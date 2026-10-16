"""
"É um documento de identidade?" -- sem conferir QUEM é a pessoa.

Antes, na coleta acadêmica (DOCUMENTO_VERIFICAR_IDENTIDADE=0), qualquer imagem válida
passava, até uma foto sem conteúdo. Agora cada foto enviada precisa:

1. ter conteúdo (não pode ser lisa/escura/branca/só desfoque): variação de tons e
   densidade de bordas mínimas;
2. e o conjunto (frente + verso) precisa mostrar sinais de documento de identidade:
   termos impressos em RG/CNH/CIN/passaporte lidos pelo OCR, formato de CPF/data,
   MRZ, QR code ou a foto 3x4 impressa (só a PRESENÇA de um rosto; nada é comparado
   com a selfie).

CPF, nome e rosto da pessoa NÃO são conferidos aqui -- isso continua desligado na coleta
acadêmica (ver documento_service).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from fastapi import HTTPException

from app.services import ocr_service

logger = logging.getLogger("payflow.kyc")

RECUSA = ("Não reconhecemos um documento de identidade na foto. Envie a frente e o verso do "
          "RG, CNH, CIN ou passaporte, inteiros, nítidos e sem reflexo.")
RECUSA_VAZIA = ("A foto do documento parece vazia ou desfocada. Fotografe o documento inteiro, "
                "com boa luz e sem reflexo.")

# Imagem com conteúdo: desvio-padrão do cinza e fração de pixels de borda (Canny).
DESVIO_MIN = 18.0
BORDAS_MIN = 0.012

# Termos impressos em documentos brasileiros de identidade (texto já normalizado:
# maiúsculo, sem acento). Fortes quase só aparecem em documento; fracos, em muita coisa.
TERMOS_FORTES = (
    "REPUBLICA FEDERATIVA", "CARTEIRA DE IDENTIDADE", "REGISTRO GERAL", "CARTEIRA NACIONAL",
    "HABILITACAO", "DETRAN", "SEGURANCA PUBLICA", "INSTITUTO DE IDENTIFICACAO", "FILIACAO",
    "NATURALIDADE", "ORGAO EMISSOR", "ORGAO EXPEDIDOR", "DOC IDENTIDADE", "PASSAPORTE",
    "PASSPORT", "IDENTIDADE", "CEDULA", "POLEGAR", "DENATRAN", "SENATRAN",
)
TERMOS_FRACOS = (
    "BRASIL", "NOME", "NASCIMENTO", "VALIDADE", "CPF", "ASSINATURA", "CATEGORIA",
    "EXPEDICAO", "EMISSAO", "PERMISSAO", "REGISTRO", "MINISTERIO", "SEXO", "NACIONALIDADE",
)
PONTOS_SO_TEXTO = 3
PONTOS_COM_ROSTO = 2

_CPF_FORMATO = re.compile(r"\d{3}\.?\d{3}\.?\d{3}\s?-?\s?\d{2}")
_DATA_FORMATO = re.compile(r"\b\d{2}[/.-]\d{2}[/.-]\d{4}\b")


@dataclass
class Evidencias:
    pontos: int = 0
    termos: list[str] = field(default_factory=list)
    rosto_impresso: bool = False
    qr: bool = False
    mrz: bool = False
    texto: str | None = None

    def resumo(self) -> dict:
        return {"pontos_texto": self.pontos, "termos": self.termos[:8], "rosto_impresso": self.rosto_impresso,
                "qr": self.qr, "mrz": self.mrz}


def tem_conteudo(img) -> bool:
    import cv2
    import numpy as np

    cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if float(np.std(cinza)) < DESVIO_MIN:
        return False
    bordas = cv2.Canny(cinza, 50, 150)
    return float(np.count_nonzero(bordas)) / bordas.size >= BORDAS_MIN


def pontuar_texto(texto: str) -> tuple[int, list[str]]:
    """Pontos de 'cara de documento' no texto do OCR (forte = 2, fraco/formato = 1)."""
    norm = " ".join(ocr_service.normalizar(texto).split())
    achados = [t for t in TERMOS_FORTES if t in norm]
    pontos = 2 * len(achados)
    fracos = [t for t in TERMOS_FRACOS if re.search(rf"\b{t}\b", norm)]
    pontos += len(fracos)
    if _CPF_FORMATO.search(texto or ""):
        pontos += 1
        fracos.append("formato_cpf")
    if _DATA_FORMATO.search(texto or ""):
        pontos += 1
        fracos.append("formato_data")
    return pontos, achados + fracos


def _rosto_impresso(imagens) -> bool:
    """Há uma foto 3x4 no documento? Só detecção (YuNet), sem embedding/comparação."""
    try:
        from app.services import face_engine

        m = face_engine.motor()
        if not hasattr(m, "detectar"):
            return False
        return any(r.score >= 0.6 and min(r.w, r.h) >= 24 for img in imagens for r in m.detectar(img))
    except Exception:  # sem modelo/stub: não é evidência, mas também não derruba o envio
        logger.info("Detector de rosto indisponível para conferir o documento.")
        return False


def coletar(imagens, provedor: str) -> Evidencias:
    ev = Evidencias()
    ev.qr = any(ocr_service.ler_qr(img) for img in imagens)
    ev.rosto_impresso = _rosto_impresso(imagens)
    if provedor == "tesseract":
        try:
            ev.texto = "\n".join(ocr_service.extrair_texto(img) for img in imagens)
        except Exception:
            logger.warning("OCR falhou ao conferir o documento.", exc_info=True)
            ev.texto = None
        if ev.texto is not None:
            ev.pontos, ev.termos = pontuar_texto(ev.texto)
            ev.mrz = ocr_service.ler_mrz(ev.texto) is not None
    return ev


def eh_documento(ev: Evidencias, provedor: str) -> bool:
    if ev.mrz or ev.qr:
        return True
    if ev.texto is None:
        # Sem OCR (ou OCR falhou): sem como ler; exige ao menos a foto 3x4 impressa.
        return ev.rosto_impresso
    return ev.pontos >= PONTOS_SO_TEXTO or (ev.rosto_impresso and ev.pontos >= PONTOS_COM_ROSTO)


def conferir(imagens, provedor: str) -> Evidencias:
    """Levanta 400 se alguma foto não tiver conteúdo ou se o conjunto não parecer um
    documento de identidade. Devolve as evidências (e o texto do OCR, para reuso)."""
    if provedor == "stub":
        return Evidencias(texto="")
    if not all(tem_conteudo(img) for img in imagens):
        raise HTTPException(status_code=400, detail=RECUSA_VAZIA)
    ev = coletar(imagens, provedor)
    if not eh_documento(ev, provedor):
        logger.info("Documento recusado por não parecer identidade: %s", ev.resumo())
        raise HTTPException(status_code=400, detail=RECUSA)
    return ev
