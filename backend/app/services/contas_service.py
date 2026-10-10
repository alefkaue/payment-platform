"""
Abertura de contas: pessoa (PF) e empresa (PJ).

PESSOA (KYC):
  CPF válido + nascimento + e-mail + celular + senha forte
  -> prova de vida de CADASTRO (piscar 3x, sorrir, virar p/ os dois lados)
  -> documento de identidade: OCR confere CPF/nome/nascimento/validade, MRZ, QR, e
     o ROSTO DO DOCUMENTO é comparado com a selfie da prova de vida
  -> reprovado: a conta NÃO é criada (o caso fica registrado, sem a imagem);
     aprovado / em análise: conta criada com esse status de KYC.

EMPRESA (KYB):
  quem abre é uma PESSOA já logada, com identidade verificada -- ela vira o
  REPRESENTANTE LEGAL e o primeiro admin. CNPJ válido e ATIVO no provedor; se o
  provedor traz o quadro de sócios, o CPF dela precisa estar nele. Documentos
  societários (contrato social / CCMEI / cartão CNPJ) são validados e conferidos
  pelo CNPJ. Os demais usuários entram por CONVITE (equipe_service) -- cada um
  com o próprio login.
"""

from datetime import date

from fastapi import HTTPException

from app.core import security
from app.core.config import get_settings
from app.core.documentos import cnpj_valido, cpf_valido, normalizar_celular, somente_digitos
from app.db.models import RegimeApuracao
from app.repositories.exceptions import (CnpjDuplicadoError, CpfDuplicadoError, EmailDuplicadoError,
                                         RostoDuplicadoError, CadastroFacialIndisponivelError)
from app.repositories.repository import Repositorio
from app.services import biometria_service, cnpj_service, documento_service, senha_policy
from app.services.seguranca_service import LIMITES_PADRAO


_DUPLICADO = "Não foi possível abrir a conta com estes dados. Se você já tem conta, entre com o seu e-mail ou CPF."


def _idade(nascimento: date) -> int:
    hoje = date.today()
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def criar_pessoa(repo: Repositorio, *, nome: str, email: str, senha: str, cpf: str, prova,
                 dispositivo_hash: str | None, ip: str | None, data_nascimento: date | None = None,
                 celular: str | None = None, documento=None) -> dict:
    s = get_settings()
    cpf = somente_digitos(cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=400, detail="CPF inválido.")
    if data_nascimento is not None and not (18 <= _idade(data_nascimento) <= 120):
        raise HTTPException(status_code=400, detail="É preciso ter 18 anos ou mais para abrir conta.")
    cel = None
    if celular:
        cel = normalizar_celular(celular)
        if cel is None:
            raise HTTPException(status_code=400, detail="Celular inválido.")
    senha_policy.validar(senha, email=email, cpf=cpf, nome=nome)
    # Mesma resposta para e-mail ou CPF já usados: não diz QUAL dado existe na base
    # (enumeração de clientes). O limite por IP do cadastro segura a varredura.
    if repo.obter_usuario_por_email(email) or repo.obter_usuario_por_cpf(cpf):
        raise HTTPException(status_code=409, detail=_DUPLICADO)
    if s.kyc_documento_obrigatorio and (documento is None or data_nascimento is None or not celular):
        raise HTTPException(status_code=400, detail="Para abrir a conta, envie data de nascimento, celular e um documento de identidade.")

    template = biometria_service.cadastrar(repo, prova, usuario_id=None)

    kyc = None
    if documento is not None:
        kyc = documento_service.analisar_documento_pessoa(
            tipo=documento.tipo, frente_b64=documento.frente, verso_b64=documento.verso, nome=nome, cpf=cpf,
            data_nascimento=data_nascimento, template_selfie=template,
        )
        if repo.documento_ja_usado(kyc["sha256"]):
            # As mesmas imagens de documento já abriram outra conta: uma conta por documento.
            raise HTTPException(status_code=409, detail=_DUPLICADO)
        if kyc["status"] == "reprovado":
            documento_service.registrar_caso_pessoa(repo, kyc, usuario_id=None)
            repo.registrar_log(ator=email.lower().strip(), acao="kyc_reprovado", ip=ip, detalhe={"motivos": kyc["motivos"]})
            raise HTTPException(status_code=422, detail="Não foi possível confirmar sua identidade: " + " ".join(kyc["motivos"]))

    try:
        conta = repo.criar_pessoa(
            nome=nome, email=email, cpf=cpf, senha_hash=security.hash_senha(senha),
            embedding_cifrado=security.cifrar_embedding(template["vetor"], template["modelo"]),
            limites_padrao=LIMITES_PADRAO["PF"], data_nascimento=data_nascimento, celular=cel,
            kyc_status=kyc["status"] if kyc else "pendente",
        )
    except (EmailDuplicadoError, CpfDuplicadoError, RostoDuplicadoError):
        raise HTTPException(status_code=409, detail=_DUPLICADO) from None
    except CadastroFacialIndisponivelError:
        raise HTTPException(status_code=503, detail="Não foi possível conferir o cadastro facial. Procure o suporte.") from None

    uid = conta["usuario_id"]
    if kyc:
        documento_service.registrar_caso_pessoa(repo, kyc, usuario_id=uid)
    if dispositivo_hash:
        # A prova de vida foi feita neste aparelho: ele já nasce confiável.
        repo.registrar_dispositivo(usuario_id=uid, id_hash=dispositivo_hash, nome=None, confiavel=True)
    repo.registrar_sessao_mfa(tipo="cadastro", sucesso=True, usuario_id=uid, ip=ip)
    repo.registrar_log(ator=email.lower().strip(), acao="criar_conta_pf", ip=ip, usuario_id=uid,
                       detalhe={"carteira_id": conta["carteira_id"], "kyc": kyc["status"] if kyc else "pendente"})
    return {**conta, "kyc": {"status": kyc["status"], "motivos": kyc["motivos"]} if kyc else {"status": "pendente", "motivos": []}}


def criar_empresa(repo: Repositorio, *, usuario: dict, cnpj: str, razao_social: str | None, nome_fantasia: str | None,
                  porte: str, regime: RegimeApuracao, ip: str | None, setor: str | None = None,
                  documentos: list | None = None) -> dict:
    s = get_settings()
    cnpj = somente_digitos(cnpj)
    if not cnpj_valido(cnpj):
        raise HTTPException(status_code=400, detail="CNPJ inválido.")
    if not usuario.get("cpf"):
        raise HTTPException(status_code=400, detail="Só uma pessoa com CPF cadastrado pode abrir conta de empresa.")
    if s.kyc_documento_obrigatorio:
        if usuario.get("kyc_status") not in ("aprovado", "em_analise"):
            raise HTTPException(status_code=403, detail="Conclua a verificação de identidade antes de abrir a conta da empresa.")
        if not documentos:
            raise HTTPException(status_code=400, detail="Envie ao menos um documento da empresa (contrato social, CCMEI ou cartão CNPJ).")
    if porte == "MEI" and regime != RegimeApuracao.MEI:
        regime = RegimeApuracao.MEI

    dados, provedor = cnpj_service.consultar(cnpj)
    if dados.situacao != "ATIVA":
        raise HTTPException(status_code=400, detail=f"CNPJ com situação '{dados.situacao}' na Receita. Só empresas ativas podem abrir conta.")
    socio = cnpj_service.eh_socio(dados, cpf=usuario["cpf"], nome=usuario["nome"])
    if socio is False:
        raise HTTPException(
            status_code=403,
            detail="Seu CPF não aparece no quadro de sócios desta empresa. Peça a um sócio para abrir a conta e te convidar.",
        )

    # Documentos analisados ANTES de criar a conta: arquivo inválido não deixa conta pela metade.
    analises = [documento_service.analisar_documento_empresa(tipo=d.tipo, arquivo_b64=d.arquivo, cnpj=cnpj)
                for d in (documentos or [])]

    try:
        conta = repo.criar_empresa(
            usuario_id=usuario["id"], cnpj=cnpj, razao_social=razao_social or dados.razao_social,
            nome_fantasia=nome_fantasia or dados.nome_fantasia, porte=porte, regime_apuracao=regime,
            cnae=dados.cnae, situacao_cadastral=dados.situacao, verificada_por=provedor,
            limites_padrao=LIMITES_PADRAO["PJ"], setor=setor,
        )
    except CnpjDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    eid = conta["empresa_id"]
    for a in analises:
        repo.registrar_documento_empresa(empresa_id=eid, tipo=a["tipo"], mime=a["mime"], tamanho=a["tamanho"],
                                         sha256=a["sha256"], status=a["status"], verificacoes=a["verificacoes"],
                                         enviado_por=usuario["id"])
    kyb = documento_service.kyb_status(repo, eid, representante=usuario)
    repo.atualizar_kyb_status(eid, kyb)
    repo.registrar_log(ator=usuario["email"], acao="criar_conta_pj", ip=ip, usuario_id=usuario["id"], empresa_id=eid,
                       detalhe={"provedor_cnpj": provedor, "socio_confirmado": socio, "porte": porte, "kyb": kyb,
                                "documentos": [a["tipo"] for a in analises]})
    return {**conta, "kyb_status": kyb}


def enviar_documento_empresa(repo: Repositorio, *, conta: dict, usuario: dict, tipo: str, arquivo_b64: str,
                             ip: str | None) -> dict:
    empresa = repo.obter_empresa(conta["empresa_id"])
    a = documento_service.analisar_documento_empresa(tipo=tipo, arquivo_b64=arquivo_b64, cnpj=empresa["cnpj"])
    d = repo.registrar_documento_empresa(empresa_id=empresa["id"], tipo=a["tipo"], mime=a["mime"], tamanho=a["tamanho"],
                                         sha256=a["sha256"], status=a["status"], verificacoes=a["verificacoes"],
                                         enviado_por=usuario["id"])
    rep_id = empresa["representante_usuario_id"]
    rep = repo.obter_usuario_por_id(rep_id) if rep_id else None
    repo.atualizar_kyb_status(empresa["id"], documento_service.kyb_status(repo, empresa["id"], representante=rep or usuario))
    repo.registrar_log(ator=usuario["email"], acao="documento_empresa_enviado", ip=ip, usuario_id=usuario["id"],
                       empresa_id=empresa["id"], detalhe={"tipo": tipo, "status": a["status"]})
    return d
