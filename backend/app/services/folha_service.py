"""
Folha de pagamento da empresa: salário só para FUNCIONÁRIO cadastrado, e só para
a conta pessoal DELE.

O ponto de segurança: o pedido de pagamento traz apenas `funcionario_id` (e,
opcionalmente, o valor). O DESTINO é resolvido no servidor -- a conta PF da
Astro cujo titular tem o CPF daquele funcionário. Não existe campo "conta de
destino" que um operador mal-intencionado (ou um token roubado) pudesse trocar
para desviar salário para terceiros. Funcionário sem conta Astro: o item falha
com a orientação de abrir conta (ou pagar por outro meio).

Alçada vale sobre o TOTAL da folha: acima dela, a folha inteira vira UMA operação
pendente de aprovação (com 2 aprovações na grande empresa, se passar do limite).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.core.documentos import cpf_valido, mascarar_cpf, somente_digitos
from app.db.models import AuthMetodo, PapelVinculo
from app.deps import exigir_papel, exigir_pj
from app.repositories.exceptions import CpfDuplicadoError
from app.repositories.repository import Repositorio
from app.services import pagamento_service, politica_pj, seguranca_service


def _log(repo, autor, conta, acao, ip, **detalhe):
    repo.registrar_log(ator=autor["email"], acao=acao, ip=ip, usuario_id=autor["id"],
                       empresa_id=conta["empresa_id"], detalhe=detalhe)


def para_api(f: dict) -> dict:
    return {**f, "cpf": mascarar_cpf(f["cpf"])}


def cadastrar(repo: Repositorio, *, conta: dict, autor: dict, nome: str, cpf: str, cargo: str | None,
              salario: Decimal | None, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    cpf = somente_digitos(cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=400, detail="CPF inválido.")
    pol = politica_pj.politica(repo.obter_empresa(conta["empresa_id"])["porte"])
    if pol.max_funcionarios is not None and repo.contar_funcionarios_ativos(conta["empresa_id"]) >= pol.max_funcionarios:
        raise HTTPException(status_code=409, detail=f"MEI pode ter até {pol.max_funcionarios} funcionário(s) registrado(s).")
    try:
        f = repo.criar_funcionario(empresa_id=conta["empresa_id"], nome=nome.strip(), cpf=cpf, cargo=cargo,
                                   salario=salario, criado_por=autor["id"])
    except CpfDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _log(repo, autor, conta, "funcionario_cadastrado", ip, funcionario_id=f["id"], cpf=mascarar_cpf(cpf))
    return para_api(f)


def listar(repo: Repositorio, *, conta: dict) -> list[dict]:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR, PapelVinculo.OPERADOR)
    return [para_api(f) for f in repo.listar_funcionarios(conta["empresa_id"])]


def desligar(repo: Repositorio, *, conta: dict, autor: dict, funcionario_id: int, ip: str | None) -> None:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    if not repo.desligar_funcionario(conta["empresa_id"], funcionario_id):
        raise HTTPException(status_code=404, detail="Funcionário não encontrado.")
    _log(repo, autor, conta, "funcionario_desligado", ip, funcionario_id=funcionario_id)


def _resolver_itens(repo: Repositorio, conta: dict, itens: list) -> list[dict]:
    resolvidos = []
    vistos: set[int] = set()
    for it in itens:
        if it.funcionario_id in vistos:
            raise HTTPException(status_code=400, detail="Funcionário repetido na mesma folha.")
        vistos.add(it.funcionario_id)
        f = repo.obter_funcionario(it.funcionario_id)
        if not f or f["empresa_id"] != conta["empresa_id"] or not f["ativo"]:
            raise HTTPException(status_code=404, detail=f"Funcionário {it.funcionario_id} não encontrado nesta empresa.")
        valor = Decimal(it.valor) if it.valor is not None else f["salario"]
        if valor is None or valor <= 0:
            raise HTTPException(status_code=400, detail=f"Informe o valor do pagamento de {f['nome']}.")
        if f["conta_salario"] is None:
            raise HTTPException(status_code=409, detail=f"{f['nome']} ainda não tem conta pessoal na Astro "
                                                        "(o salário só pode ir para a conta do próprio funcionário).")
        resolvidos.append({"funcionario_id": f["id"], "nome": f["nome"], "valor": str(valor),
                           "destino_carteira_id": f["conta_salario"]["carteira_id"]})
    return resolvidos


def pagar(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list,
          descricao: str | None, biometria, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, *pagamento_service.PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)
    if not itens:
        raise HTTPException(status_code=400, detail="Folha vazia.")
    resolvidos = _resolver_itens(repo, conta, itens)
    total = sum((Decimal(r["valor"]) for r in resolvidos), Decimal("0"))
    rotulo = descricao or f"Salário {tempo.hoje_brt():%m/%Y}"

    if pagamento_service.precisa_aprovacao(conta, total):
        p = pagamento_service.criar_pendente(
            repo, conta=conta, usuario=usuario, tipo="folha", valor=total, ip=ip,
            descricao=f"{rotulo} — {len(resolvidos)} funcionário(s)",
            payload={"itens": resolvidos, "descricao": rotulo},
        )
        return {"pendente": p}

    verificacao = None
    if total > Decimal(str(get_settings().limite_facial_reais)):
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="folha")
    return {"resultados": executar(repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=resolvidos,
                                   descricao=rotulo, ip=ip, verificacao=verificacao, chave_base=None)}


def executar(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list[dict],
             descricao: str, ip: str | None, verificacao: dict | None, chave_base: str | None,
             auth_metodo: AuthMetodo | None = None) -> list[dict]:
    resultados = []
    for i, it in enumerate(itens):
        destino = repo.obter_conta(it["destino_carteira_id"])
        try:
            r = pagamento_service.transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino,
                valor=Decimal(it["valor"]), descricao=f"{descricao} — {it['nome']}"[:140],
                idempotency_key=f"{chave_base}-{i}" if chave_base else None, ip=ip, mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, sem_bloqueio_cautelar=True,
                auth_metodo=auth_metodo,
            )
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "pago",
                               "transacao_id": r["transacao"]["id"]})
        except HTTPException as e:
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "erro", "erro": str(e.detail)})
    _log(repo, usuario, conta, "folha_paga", ip, itens=len(itens),
         pagos=sum(1 for r in resultados if r["situacao"] == "pago"))
    return resultados
