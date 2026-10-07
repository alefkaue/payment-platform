"""
Cadastro de pessoas e empresas e gestão de quem opera cada empresa.

- Pessoa: CPF obrigatório e válido, senha (bcrypt), biometria com desafio. Nasce
  com carteira PF de saldo zero e limites padrão. O aparelho usado no cadastro já
  fica confiável (a prova biométrica foi feita nele).
- Empresa: criada por uma pessoa já logada. CNPJ com dígito válido, consultado no
  provedor (situação ATIVA e, quando o provedor traz o quadro de sócios, a pessoa
  precisa estar nele). Nasce com carteira PJ, limites PJ e vínculo ADMIN do criador.
- Vínculos: só ADMIN da empresa adiciona/remove pessoas e define alçadas. A
  empresa nunca fica sem pelo menos um ADMIN ativo.
"""

from decimal import Decimal

from fastapi import HTTPException

from app.core import security
from app.core.documentos import cnpj_valido, cpf_valido, somente_digitos
from app.db.models import PapelVinculo, RegimeApuracao
from app.repositories.exceptions import CnpjDuplicadoError, CpfDuplicadoError, EmailDuplicadoError
from app.repositories.repository import Repositorio
from app.services import biometria_service, cnpj_service
from app.services.seguranca_service import LIMITES_PADRAO


def criar_pessoa(repo: Repositorio, *, nome: str, email: str, senha: str, cpf: str, prova,
                 dispositivo_hash: str | None, ip: str | None) -> dict:
    cpf = somente_digitos(cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=400, detail="CPF inválido.")
    if repo.obter_usuario_por_email(email):
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse e-mail.")

    embedding = biometria_service.cadastrar(repo, prova, usuario_id=None)
    try:
        conta = repo.criar_pessoa(
            nome=nome, email=email, cpf=cpf, senha_hash=security.hash_senha(senha),
            embedding_cifrado=security.cifrar_embedding(embedding), limites_padrao=LIMITES_PADRAO["PF"],
        )
    except (EmailDuplicadoError, CpfDuplicadoError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    if dispositivo_hash:
        repo.registrar_dispositivo(usuario_id=conta["usuario_id"], id_hash=dispositivo_hash, nome=None, confiavel=True)
    repo.registrar_sessao_mfa(tipo="cadastro", sucesso=True, usuario_id=conta["usuario_id"], ip=ip)
    repo.registrar_log(ator=email.lower().strip(), acao="criar_conta_pf", ip=ip, detalhe={"carteira_id": conta["carteira_id"]})
    return conta


def criar_empresa(repo: Repositorio, *, usuario: dict, cnpj: str, razao_social: str | None, nome_fantasia: str | None,
                  porte: str, regime: RegimeApuracao, ip: str | None, setor: str | None = None) -> dict:
    cnpj = somente_digitos(cnpj)
    if not cnpj_valido(cnpj):
        raise HTTPException(status_code=400, detail="CNPJ inválido.")
    if not usuario.get("cpf"):
        raise HTTPException(status_code=400, detail="Só uma pessoa com CPF cadastrado pode abrir conta de empresa.")
    if porte == "MEI" and regime != RegimeApuracao.MEI:
        regime = RegimeApuracao.MEI

    dados, provedor = cnpj_service.consultar(cnpj)
    if dados.situacao != "ATIVA":
        raise HTTPException(status_code=400, detail=f"CNPJ com situação '{dados.situacao}' na Receita. Só empresas ativas podem abrir conta.")
    socio = cnpj_service.eh_socio(dados, cpf=usuario["cpf"], nome=usuario["nome"])
    if socio is False:
        raise HTTPException(
            status_code=403,
            detail="Seu CPF não aparece no quadro de sócios desta empresa. Peça a um sócio para abrir a conta e te adicionar.",
        )

    try:
        conta = repo.criar_empresa(
            usuario_id=usuario["id"], cnpj=cnpj, razao_social=razao_social or dados.razao_social,
            nome_fantasia=nome_fantasia or dados.nome_fantasia, porte=porte, regime_apuracao=regime,
            cnae=dados.cnae, situacao_cadastral=dados.situacao, verificada_por=provedor,
            limites_padrao=LIMITES_PADRAO["PJ"], setor=setor,
        )
    except CnpjDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    repo.registrar_log(ator=usuario["email"], acao="criar_conta_pj", ip=ip,
                       detalhe={"empresa_id": conta["empresa_id"], "provedor_cnpj": provedor, "socio_confirmado": socio})
    return conta


def adicionar_vinculo(repo: Repositorio, *, conta: dict, autor: dict, email: str, papel: PapelVinculo,
                      alcada: Decimal | None, ip: str | None) -> dict:
    pessoa = repo.obter_usuario_por_email(email)
    if not pessoa or not pessoa.get("cpf"):
        raise HTTPException(status_code=404, detail="Não há pessoa com conta Astro nesse e-mail. Ela precisa se cadastrar primeiro.")
    if pessoa["id"] == autor["id"] and papel != PapelVinculo.ADMIN and repo.contar_admins_ativos(conta["empresa_id"]) <= 1:
        raise HTTPException(status_code=400, detail="A empresa precisa de pelo menos um administrador.")
    v = repo.criar_ou_atualizar_vinculo(empresa_id=conta["empresa_id"], usuario_id=pessoa["id"], papel=papel, alcada=alcada)
    repo.registrar_log(ator=autor["email"], acao="vinculo_definido", ip=ip,
                       detalhe={"empresa_id": conta["empresa_id"], "usuario_id": pessoa["id"], "papel": papel.value,
                                "alcada": str(alcada) if alcada is not None else None})
    return v


def remover_vinculo(repo: Repositorio, *, conta: dict, autor: dict, vinculo_id: int, ip: str | None) -> None:
    alvo = next((v for v in repo.listar_vinculos(conta["empresa_id"]) if v["id"] == vinculo_id), None)
    if alvo is None:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado.")
    if alvo["papel"] == PapelVinculo.ADMIN.value and alvo["ativo"] and repo.contar_admins_ativos(conta["empresa_id"]) <= 1:
        raise HTTPException(status_code=400, detail="A empresa precisa de pelo menos um administrador.")
    repo.desativar_vinculo(vinculo_id, conta["empresa_id"])
    repo.registrar_log(ator=autor["email"], acao="vinculo_removido", ip=ip, detalhe={"vinculo_id": vinculo_id})
