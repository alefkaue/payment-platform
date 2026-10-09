"""
Equipe da conta PJ: quem acessa, com qual papel e alçada.

Modelo (igual aos bancos empresariais -- Usuário Master x Secundários):
1. O ADMIN da empresa convida informando o CPF (+ nome, e-mail, celular, cargo),
   o papel e a alçada. Nada de criar senha para o funcionário.
2. O vínculo nasce PENDENTE. Só a pessoa DONA DAQUELE CPF -- com conta própria e
   identidade verificada -- vê o convite e aceita confirmando com o rosto. Cada
   pessoa usa o próprio login; o representante e o contador NUNCA dividem acesso.
3. Dar poder (admin/aprovador, alçada maior, reativar) exige o rosto de quem
   concede; na GRANDE empresa, fica AGUARDANDO até outro admin aprovar.
4. Suspender (temporário), reativar e revogar ficam registrados na auditoria. A
   empresa nunca fica sem um admin ativo.

As regras por porte estão em politica_pj.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.documentos import cpf_valido, mascarar_cpf, somente_digitos
from app.db.models import PapelVinculo
from app.deps import exigir_papel, exigir_pj
from app.repositories.exceptions import CpfDuplicadoError
from app.repositories.repository import Repositorio
from app.services import politica_pj, seguranca_service

PODEROSOS = (PapelVinculo.ADMIN.value, PapelVinculo.APROVADOR.value)


def _log(repo: Repositorio, autor: dict, conta: dict, acao: str, ip: str | None, **detalhe) -> None:
    repo.registrar_log(ator=autor["email"], acao=acao, ip=ip, usuario_id=autor["id"],
                       empresa_id=conta["empresa_id"], detalhe=detalhe)


def _empresa(repo: Repositorio, conta: dict) -> dict:
    return repo.obter_empresa(conta["empresa_id"])


def _validar_papel_alcada(pol: politica_pj.Politica, papel: str, alcada: Decimal | None) -> Decimal | None:
    if papel not in pol.papeis_convidaveis:
        raise HTTPException(status_code=403, detail=f"Na conta {pol.porte}, o papel '{papel}' não pode ser concedido.")
    if papel == PapelVinculo.ADMIN.value:
        return None  # admin não tem alçada (aprova/administra tudo)
    if papel == PapelVinculo.CONSULTA.value:
        return Decimal("0")  # só vê -- nunca movimenta
    if alcada is None and pol.operador_exige_alcada and papel == PapelVinculo.OPERADOR.value:
        raise HTTPException(status_code=400, detail=f"Na conta {pol.porte}, operador precisa de alçada definida.")
    return alcada


def _quatro_olhos(repo: Repositorio, pol: politica_pj.Politica, conta: dict) -> bool:
    return pol.quatro_olhos_acesso and repo.contar_admins_ativos(conta["empresa_id"]) >= 2


def para_api(v: dict, *, eu_id: int | None = None) -> dict:
    """Vínculo para a tela de equipe: CPF sempre mascarado."""
    return {
        "id": v["id"], "usuario_id": v["usuario_id"], "nome": v["nome"], "email": v["email"],
        "cpf": mascarar_cpf(v["cpf"]) if v.get("cpf") else None, "celular": v.get("celular"), "cargo": v.get("cargo"),
        "papel": v["papel"], "alcada": v["alcada"], "status": v["status"], "ativo": v["ativo"],
        "aceito_em": v.get("aceito_em"), "status_em": v.get("status_em"), "ultimo_acesso_em": v.get("ultimo_acesso_em"),
        "criado_em": v.get("criado_em"), "criado_por_usuario_id": v.get("criado_por_usuario_id"),
        "eu": eu_id is not None and v["usuario_id"] == eu_id,
    }


# =============================================================================
# Admin: convidar / alterar / suspender / reativar / revogar
# =============================================================================


def convidar(repo: Repositorio, *, conta: dict, autor: dict, cpf: str, nome: str, email: str | None,
             celular: str | None, cargo: str | None, papel: PapelVinculo, alcada: Decimal | None, prova,
             ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    cpf = somente_digitos(cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=400, detail="CPF inválido.")
    empresa = _empresa(repo, conta)
    pol = politica_pj.politica(empresa["porte"])
    alcada = _validar_papel_alcada(pol, papel.value, alcada)
    if repo.contar_vagas_ocupadas(conta["empresa_id"]) >= pol.max_usuarios:
        raise HTTPException(status_code=409, detail=f"Limite de {pol.max_usuarios} usuários para conta {pol.porte} atingido.")

    sensivel = politica_pj.mudanca_sensivel(papel_atual=None, alcada_atual=None, papel_novo=papel.value, alcada_nova=alcada)
    if sensivel:
        seguranca_service.verificar_rosto(repo, usuario=autor, prova=prova, ip=ip, tipo="conceder_acesso")
    aguardar = sensivel and _quatro_olhos(repo, pol, conta)
    try:
        v = repo.criar_convite(empresa_id=conta["empresa_id"], cpf=cpf, nome=nome.strip(), email=email, celular=celular,
                               cargo=cargo, papel=papel, alcada=alcada, status="aguardando" if aguardar else "pendente",
                               criado_por=autor["id"])
    except CpfDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if aguardar:
        _pedir_aprovacao_acesso(repo, conta=conta, autor=autor, vinculo=v, acao="convite",
                                mudanca={"papel": papel.value, "alcada": None if alcada is None else str(alcada)}, ip=ip)
    _log(repo, autor, conta, "usuario_convidado", ip, vinculo_id=v["id"], cpf=mascarar_cpf(cpf), papel=papel.value,
         alcada=None if alcada is None else str(alcada), status=v["status"])
    return para_api(v, eu_id=autor["id"])


def _vinculo_da_empresa(repo: Repositorio, conta: dict, vinculo_id: int) -> dict:
    v = repo.obter_vinculo_por_id(vinculo_id)
    if not v or v["empresa_id"] != conta["empresa_id"]:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada nesta empresa.")
    return v


def _garantir_admin_restante(repo: Repositorio, conta: dict, v: dict) -> None:
    if v["papel"] == PapelVinculo.ADMIN.value and v["status"] == "ativo" and repo.contar_admins_ativos(conta["empresa_id"]) <= 1:
        raise HTTPException(status_code=400, detail="A empresa precisa de pelo menos um administrador ativo.")


def alterar(repo: Repositorio, *, conta: dict, autor: dict, vinculo_id: int, papel: PapelVinculo | None,
            alcada: Decimal | None, sem_limite: bool, prova, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    v = _vinculo_da_empresa(repo, conta, vinculo_id)
    if v["status"] in ("revogado", "recusado"):
        raise HTTPException(status_code=409, detail="Acesso encerrado não pode ser alterado. Convide de novo.")
    pol = politica_pj.politica(_empresa(repo, conta)["porte"])
    novo_papel = papel.value if papel else v["papel"]
    nova_alcada = None if sem_limite else (alcada if alcada is not None else v["alcada"])
    if novo_papel == v["papel"] == PapelVinculo.ADMIN.value:
        nova_alcada = None  # admin continua admin (no MEI, o titular não é "convidável")
    else:
        nova_alcada = _validar_papel_alcada(pol, novo_papel, nova_alcada)
    if v["papel"] == PapelVinculo.ADMIN.value and novo_papel != PapelVinculo.ADMIN.value:
        _garantir_admin_restante(repo, conta, v)

    sensivel = politica_pj.mudanca_sensivel(papel_atual=v["papel"], alcada_atual=v["alcada"],
                                            papel_novo=novo_papel, alcada_nova=nova_alcada)
    if sensivel:
        seguranca_service.verificar_rosto(repo, usuario=autor, prova=prova, ip=ip, tipo="conceder_acesso")
        if _quatro_olhos(repo, pol, conta):
            op = _pedir_aprovacao_acesso(repo, conta=conta, autor=autor, vinculo=v, acao="alteracao",
                                         mudanca={"papel": novo_papel, "alcada": None if nova_alcada is None else str(nova_alcada)},
                                         ip=ip)
            return {**para_api(v, eu_id=autor["id"]), "aguardando_aprovacao": True, "operacao_id": op["id"]}
    r = repo.atualizar_vinculo(vinculo_id, papel=PapelVinculo(novo_papel), alcada=nova_alcada)
    _log(repo, autor, conta, "permissao_alterada", ip, vinculo_id=vinculo_id, de={"papel": v["papel"],
         "alcada": None if v["alcada"] is None else str(v["alcada"])},
         para={"papel": novo_papel, "alcada": None if nova_alcada is None else str(nova_alcada)})
    return para_api(r, eu_id=autor["id"])


def mudar_status(repo: Repositorio, *, conta: dict, autor: dict, vinculo_id: int, acao: str, prova,
                 ip: str | None) -> dict:
    """acao: suspender | reativar | revogar."""
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    v = _vinculo_da_empresa(repo, conta, vinculo_id)
    transicoes = {
        "suspender": ({"ativo"}, "suspenso", "usuario_suspenso"),
        "reativar": ({"suspenso"}, "ativo", "usuario_reativado"),
        "revogar": ({"ativo", "suspenso", "pendente", "aguardando"}, "revogado", "usuario_revogado"),
    }
    if acao not in transicoes:
        raise HTTPException(status_code=400, detail="Ação inválida.")
    de, para, evento = transicoes[acao]
    if v["status"] not in de:
        raise HTTPException(status_code=409, detail=f"Não é possível {acao} um acesso '{v['status']}'.")
    if acao in ("suspender", "revogar"):
        _garantir_admin_restante(repo, conta, v)
    if acao == "reativar":
        pol = politica_pj.politica(_empresa(repo, conta)["porte"])
        seguranca_service.verificar_rosto(repo, usuario=autor, prova=prova, ip=ip, tipo="reativar_acesso")
        if v["papel"] in PODEROSOS and _quatro_olhos(repo, pol, conta):
            op = _pedir_aprovacao_acesso(repo, conta=conta, autor=autor, vinculo=v, acao="reativacao",
                                         mudanca={"status": "ativo"}, ip=ip)
            return {**para_api(v, eu_id=autor["id"]), "aguardando_aprovacao": True, "operacao_id": op["id"]}
    # Suspenso/revogado perde o acesso na hora: as checagens de permissão leem
    # `ativo`, que acompanha o status.
    r = repo.atualizar_vinculo(vinculo_id, status=para)
    _log(repo, autor, conta, evento, ip, vinculo_id=vinculo_id, de=v["status"], para=para)
    return para_api(r, eu_id=autor["id"])


def listar(repo: Repositorio, *, conta: dict, usuario: dict) -> list[dict]:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    return [para_api(v, eu_id=usuario["id"]) for v in repo.listar_vinculos(conta["empresa_id"])
            if v["status"] not in ("recusado",)]


# =============================================================================
# Quatro olhos na gestão de acesso (GRANDE)
# =============================================================================


def _pedir_aprovacao_acesso(repo: Repositorio, *, conta: dict, autor: dict, vinculo: dict, acao: str,
                            mudanca: dict, ip: str | None) -> dict:
    from app.services import pagamento_service  # import tardio (ciclo)

    nome = vinculo.get("nome") or "pessoa"
    return pagamento_service.criar_pendente(
        repo, conta=conta, usuario=autor, tipo="acesso", valor=Decimal("0"), ip=ip,
        descricao=f"Acesso de {nome}: {acao} ({mudanca.get('papel') or mudanca.get('status')})",
        payload={"vinculo_id": vinculo["id"], "acao": acao, "mudanca": mudanca},
    )


def aplicar_aprovacao_acesso(repo: Repositorio, *, conta: dict, aprovador: dict, payload: dict, ip: str | None) -> dict:
    """Executada quando outro admin aprova a operação pendente tipo 'acesso'."""
    v = repo.obter_vinculo_por_id(payload["vinculo_id"])
    if not v or v["empresa_id"] != conta["empresa_id"]:
        raise HTTPException(status_code=404, detail="Vínculo não existe mais.")
    m = payload["mudanca"]
    if payload["acao"] == "convite":
        if v["status"] != "aguardando":
            raise HTTPException(status_code=409, detail="Este convite não está mais aguardando aprovação.")
        r = repo.atualizar_vinculo(v["id"], status="pendente")
    elif payload["acao"] == "reativacao":
        r = repo.atualizar_vinculo(v["id"], status="ativo")
    else:
        r = repo.atualizar_vinculo(v["id"], papel=PapelVinculo(m["papel"]),
                                   alcada=None if m.get("alcada") is None else Decimal(m["alcada"]))
    _log(repo, aprovador, conta, "acesso_aprovado", ip, vinculo_id=v["id"], mudanca=payload["acao"])
    return r


# =============================================================================
# A própria pessoa: ver, aceitar, recusar convites
# =============================================================================


def meus_convites(repo: Repositorio, *, usuario: dict) -> list[dict]:
    if not usuario.get("cpf"):
        return []
    return [{**para_api(c), "empresa": c["empresa"], "convidado_por": c["convidado_por"]}
            for c in repo.convites_do_cpf(usuario["cpf"])]


def aceitar(repo: Repositorio, *, usuario: dict, vinculo_id: int, prova, ip: str | None) -> dict:
    if not usuario.get("cpf"):
        raise HTTPException(status_code=400, detail="Só uma pessoa com CPF cadastrado pode aceitar convites.")
    if get_settings().kyc_documento_obrigatorio and usuario.get("kyc_status") not in ("aprovado", "em_analise"):
        raise HTTPException(status_code=403, detail="Conclua a verificação de identidade antes de acessar uma empresa.")
    v = repo.obter_vinculo_por_id(vinculo_id)
    if not v or v.get("cpf") != usuario["cpf"] or v["status"] != "pendente":
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    seguranca_service.verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="aceitar_convite")
    r = repo.aceitar_convite(vinculo_id, usuario["id"], usuario["cpf"])
    if r is None:
        raise HTTPException(status_code=409, detail="Este convite já foi usado ou você já tem acesso a esta empresa.")
    repo.registrar_log(ator=usuario["email"], acao="convite_aceito", ip=ip, usuario_id=usuario["id"],
                       empresa_id=r["empresa_id"], detalhe={"vinculo_id": vinculo_id, "papel": r["papel"]})
    return para_api(r, eu_id=usuario["id"])


def recusar(repo: Repositorio, *, usuario: dict, vinculo_id: int, ip: str | None) -> None:
    v = repo.obter_vinculo_por_id(vinculo_id)
    if not v or v.get("cpf") != usuario.get("cpf") or v["status"] != "pendente":
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    repo.atualizar_vinculo(vinculo_id, status="recusado")
    repo.registrar_log(ator=usuario["email"], acao="convite_recusado", ip=ip, usuario_id=usuario["id"],
                       empresa_id=v["empresa_id"], detalhe={"vinculo_id": vinculo_id})
