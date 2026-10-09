"""
KYC (pessoa) e KYB (empresa): análise de documentos.

Pessoa -- documento de identidade (RG, CNH, CIN ou passaporte):
  1. arquivo validado pela assinatura real (core/arquivos), sem guardar a imagem;
  2. OCR (ocr_service) e conferência com o que foi declarado: CPF (com DV),
     nome (tolerante a erro de OCR), data de nascimento, validade;
  3. MRZ (CIN/passaporte): dígitos verificadores ICAO + nascimento batendo;
  4. QR code presente (CNH digital/CIN) -- só registramos SE há e se aponta para
     domínio gov.br, nunca o conteúdo;
  5. ROSTO DO DOCUMENTO x SELFIE da prova de vida (SFace). É o que liga o
     documento à pessoa que está na câmera agora.

Decisão (sem aprovar às cegas):
  - reprovado: algo CONTRADIZ (CPF de outra pessoa, nascimento diferente,
    documento vencido, MRZ adulterada, rosto claramente de outra pessoa);
  - aprovado: tudo que foi conferido bateu, inclusive o rosto;
  - em_analise: faltou como conferir algo (sem OCR, foto ruim, rosto na faixa
    de dúvida) -- vai para a fila de análise humana (admin).

Empresa -- contrato social / CCMEI / cartão CNPJ / procuração: arquivo validado
(PDF sem conteúdo ativo), texto extraído (pypdf ou OCR) e conferido se o CNPJ da
empresa aparece nele.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import HTTPException

from app.core import arquivos, tempo
from app.core.config import get_settings
from app.core.documentos import mascarar_cpf, mascarar_nome, somente_digitos
from app.services import biometria_service, ocr_service

logger = logging.getLogger("payflow.kyc")

TIPOS_DOC_PESSOA = ("rg", "cnh", "cin", "passaporte")
TIPOS_DOC_EMPRESA = ("contrato_social", "ccmei", "cartao_cnpj", "procuracao", "outro")
# Rosto do documento abaixo disto (em relação ao limiar) é "claramente outra pessoa".
_MARGEM_REPROVA_ROSTO = 0.12


def _decodificar(bruto: bytes):
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(bruto, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Não foi possível abrir a imagem do documento.")
    return img


def analisar_documento_pessoa(*, tipo: str, frente_b64: str, verso_b64: str | None, nome: str, cpf: str,
                              data_nascimento: date | None, template_selfie: dict | None) -> dict:
    """Devolve {status, provedor, sha256, campos, verificacoes, motivos, nivel_risco}."""
    if tipo not in TIPOS_DOC_PESSOA:
        raise HTTPException(status_code=400, detail="Tipo de documento inválido (use rg, cnh, cin ou passaporte).")
    s = get_settings()
    bruto, _, sha = arquivos.validar_arquivo(frente_b64, permitidos=arquivos.IMAGENS, limite_bytes=s.documento_max_bytes)
    imagens = [_decodificar(bruto)]
    if verso_b64:
        bruto_v, _, sha_v = arquivos.validar_arquivo(verso_b64, permitidos=arquivos.IMAGENS, limite_bytes=s.documento_max_bytes)
        imagens.append(_decodificar(bruto_v))
        sha = f"{sha}:{sha_v}"

    cpf = somente_digitos(cpf)
    prov = ocr_service.provedor()
    v: dict = {}
    motivos: list[str] = []
    campos: dict = {"nome": mascarar_nome(nome), "cpf": mascarar_cpf(cpf)}

    # ---------------------------------------------------------- texto
    if prov == "stub":
        v.update({"cpf": True, "nome": True, "nascimento": True, "texto": "stub"})
    elif prov == "sem_ocr":
        v.update({"cpf": None, "nome": None, "nascimento": None, "texto": "nao_conferido"})
        motivos.append("Texto do documento não conferido automaticamente (sem OCR): análise humana.")
    else:
        texto = "\n".join(ocr_service.extrair_texto(img) for img in imagens)
        cpfs = ocr_service.encontrar_cpfs(texto)
        datas = ocr_service.encontrar_datas(texto)
        v["cpf"] = (cpf in cpfs) if cpfs else None
        if cpfs and cpf not in cpfs:
            motivos.append("O CPF lido no documento é diferente do informado.")
        v["nome"] = ocr_service.nome_confere(nome, texto)
        if data_nascimento:
            v["nascimento"] = (data_nascimento in datas) if datas else None
        hoje = tempo.hoje_brt()
        futuras = [d for d in datas if d > hoje]
        if tipo in ("cnh", "cin", "passaporte"):
            if futuras:
                campos["validade"] = max(futuras).isoformat()
                v["validade"] = True
            else:
                # Documento com validade e nenhuma data futura: vencido ou ilegível.
                recentes = [d for d in datas if data_nascimento is None or d.year > data_nascimento.year + 15]
                v["validade"] = False if recentes else None
                if recentes:
                    motivos.append("Documento vencido.")
        mrz = ocr_service.ler_mrz(texto)
        if mrz:
            v["mrz"] = mrz["valido"]
            if not mrz["valido"]:
                motivos.append("Zona de leitura mecânica (MRZ) com dígitos verificadores inválidos.")
            if mrz["nascimento"] and data_nascimento and mrz["nascimento"] != data_nascimento:
                v["mrz"] = False
                motivos.append("Data de nascimento da MRZ não confere.")
        v["texto"] = "tesseract"

    # ---------------------------------------------------------- QR
    qrs = [q for img in imagens for q in ocr_service.ler_qr(img)]
    v["qr"] = {"encontrado": bool(qrs), "dominio_gov": any("gov.br" in q.lower() for q in qrs)}

    # ---------------------------------------------------------- rosto
    if biometria_service.stub_ligado() or template_selfie is None:
        v["rosto"] = "stub" if biometria_service.stub_ligado() else None
        rosto_ok = True if biometria_service.stub_ligado() else None
        if template_selfie is None and not biometria_service.stub_ligado():
            motivos.append("Sem selfie para comparar com o documento.")
    else:
        t_doc = None
        for img in imagens:
            t_doc = biometria_service.template_de_documento(img)
            if t_doc:
                break
        if t_doc is None:
            rosto_ok = None
            v["rosto"] = {"encontrado": False}
            motivos.append("Não encontramos o rosto na foto do documento.")
        else:
            sim = biometria_service.similaridade(t_doc, template_selfie["vetor"])
            limiar = s.face_doc_limiar_cosseno
            rosto_ok = sim >= limiar
            v["rosto"] = {"encontrado": True, "similaridade": round(sim, 4), "limiar": limiar}
            if sim < limiar - _MARGEM_REPROVA_ROSTO:
                rosto_ok = False
                motivos.append("O rosto do documento não corresponde à selfie.")
            elif not rosto_ok:
                rosto_ok = None
                motivos.append("Semelhança do rosto na faixa de dúvida: análise humana.")

    # ---------------------------------------------------------- decisão
    contradicoes = [v.get("cpf") is False, v.get("nascimento") is False, v.get("validade") is False,
                    v.get("mrz") is False, rosto_ok is False]
    conferidos = [v.get("cpf"), v.get("nome"), v.get("nascimento") if data_nascimento else True, rosto_ok]
    if any(contradicoes):
        status, risco = "reprovado", "alto"
    elif all(x is True for x in conferidos):
        status, risco = "aprovado", "baixo"
    else:
        status, risco = "em_analise", "medio"
    return {"tipo": tipo, "status": status, "provedor": prov, "sha256": sha, "campos": campos,
            "verificacoes": v, "motivos": motivos, "nivel_risco": risco}


def analisar_documento_empresa(*, tipo: str, arquivo_b64: str, cnpj: str) -> dict:
    if tipo not in TIPOS_DOC_EMPRESA:
        raise HTTPException(status_code=400, detail="Tipo de documento da empresa inválido.")
    s = get_settings()
    bruto, mime, sha = arquivos.validar_arquivo(arquivo_b64, permitidos=arquivos.DOCUMENTOS,
                                                limite_bytes=s.empresa_documento_max_bytes)
    texto = ""
    leitura = "nao_conferido"
    if mime == "application/pdf":
        texto, leitura = _texto_pdf(bruto), "pdf"
    elif ocr_service.provedor() == "tesseract":
        texto, leitura = ocr_service.extrair_texto(_decodificar(bruto)), "tesseract"
    elif ocr_service.provedor() == "stub":
        texto, leitura = cnpj, "stub"
    achou = somente_digitos(cnpj) in somente_digitos(texto) if texto else None
    # CNPJ conferido no texto -> aprovado; sem texto ou CNPJ ausente -> análise humana.
    status = "aprovado" if achou else "em_analise"
    verificacoes = {"leitura": leitura, "cnpj_encontrado": achou, "paginas_texto": bool(texto.strip()) if texto else False}
    return {"tipo": tipo, "mime": mime, "tamanho": len(bruto), "sha256": sha, "status": status, "verificacoes": verificacoes}


def _texto_pdf(bruto: bytes) -> str:
    import io

    from pypdf import PdfReader

    try:
        leitor = PdfReader(io.BytesIO(bruto))
        if len(leitor.pages) > 50:
            raise HTTPException(status_code=413, detail="PDF com páginas demais (máximo 50).")
        return "\n".join((p.extract_text() or "") for p in leitor.pages[:50])
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - PDF malformado
        raise HTTPException(status_code=400, detail="PDF inválido ou corrompido.")


# =============================================================================
# Persistência do caso
# =============================================================================


def registrar_caso_pessoa(repo, resultado: dict, *, usuario_id: int | None) -> dict:
    caso = repo.criar_caso_kyc(tipo="pf", status=resultado["status"], nivel_risco=resultado["nivel_risco"],
                               motivos=resultado["motivos"], usuario_id=usuario_id)
    repo.registrar_documento_identidade(caso_id=caso["id"], tipo=resultado["tipo"], status=resultado["status"],
                                        provedor=resultado["provedor"], sha256=resultado["sha256"],
                                        campos=resultado["campos"], verificacoes=_json(resultado["verificacoes"]))
    return caso


def _json(d: dict) -> dict:
    """Datas -> ISO para caber no JSON."""
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items()}


def kyb_status(repo, empresa_id: int, *, representante: dict) -> str:
    """aprovado = representante com KYC aprovado + ao menos um documento
    societário com o CNPJ conferido; senão em_analise."""
    docs = repo.listar_documentos_empresa(empresa_id)
    societario_ok = any(d["status"] == "aprovado" for d in docs)
    if representante.get("kyc_status") == "aprovado" and societario_ok:
        return "aprovado"
    return "em_analise"
