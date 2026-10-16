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

Regra de desligamento (R05): a folha paga só funcionário ATIVO, no momento em que o
dinheiro sai. Quem foi desligado depois do lançamento e antes da aprovação (ou da
repetição) não recebe por esta folha: o item fica com erro explicando o motivo, e a
listagem de pendências mostra o desligamento antes de alguém aprovar. Acerto e verbas
rescisórias de quem já saiu não passam pela folha: vão por Pix comum, que segue a
alçada de quem lança. Isso não diz que todo pagamento a ex-funcionário é indevido --
só que a folha não é o caminho para ele.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.documentos import cpf_valido, mascarar_cpf, somente_digitos
from app.db.models import AuthMetodo, PapelVinculo
from app.deps import exigir_papel, exigir_pj
from app.repositories.exceptions import CpfDuplicadoError, IdempotenciaConflitanteError, LimiteQuantidadeError
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
    limite = HTTPException(status_code=409, detail=f"MEI pode ter até {pol.max_funcionarios} funcionário(s) registrado(s).")
    # Checagem rápida; a que vale é refeita com a empresa travada, junto da inserção (R09).
    if pol.max_funcionarios is not None and repo.contar_funcionarios_ativos(conta["empresa_id"]) >= pol.max_funcionarios:
        raise limite
    try:
        f = repo.criar_funcionario(empresa_id=conta["empresa_id"], nome=nome.strip(), cpf=cpf, cargo=cargo,
                                   salario=salario, criado_por=autor["id"], maximo=pol.max_funcionarios)
    except CpfDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LimiteQuantidadeError:
        raise limite from None
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
        if valor is not None:
            # Forma canônica (300 == 3e2 == 300.0): a chave derivada da folha não muda (C2-01).
            valor = valor.quantize(Decimal("0.01"))
        if valor is None or valor <= 0:
            raise HTTPException(status_code=400, detail=f"Informe o valor do pagamento de {f['nome']}.")
        if f["conta_salario"] is None:
            raise HTTPException(status_code=409, detail=f"{f['nome']} ainda não tem conta pessoal na Astro "
                                                        "(o salário só pode ir para a conta do próprio funcionário).")
        resolvidos.append({"funcionario_id": f["id"], "nome": f["nome"], "valor": str(valor),
                           "destino_carteira_id": f["conta_salario"]["carteira_id"]})
    return resolvidos


def _motivo_para_nao_pagar(repo: Repositorio, conta: dict, item: dict) -> str | None:
    """R05: confere o cadastro no momento da execução, não só no lançamento."""
    f = repo.obter_funcionario(item["funcionario_id"])
    if not f or f["empresa_id"] != conta["empresa_id"]:
        return "Funcionário não está mais nesta empresa: salário não pago."
    if not f["ativo"]:
        quando = f" em {tempo.em_brt(f['desligado_em']):%d/%m/%Y}" if f["desligado_em"] else ""
        return (f"{f['nome']} foi desligado{quando}, depois do lançamento: salário não pago por esta folha. "
                "Acerto/rescisão vai por Pix comum.")
    if not f["conta_salario"] or f["conta_salario"]["carteira_id"] != item["destino_carteira_id"]:
        return f"A conta pessoal de {f['nome']} mudou desde o lançamento: lance a folha de novo."
    return None


def desligados_na_folha(repo: Repositorio, p: dict) -> list[int]:
    """Funcionários de uma folha pendente que não estão mais ativos (aviso para quem aprova)."""
    ids = []
    for it in (p.get("payload") or {}).get("itens") or []:
        f = repo.obter_funcionario(it["funcionario_id"])
        if not f or not f["ativo"] or f["empresa_id"] != p["empresa_id"]:
            ids.append(it["funcionario_id"])
    return ids


def _chave_da_folha(conta: dict, rotulo: str, resolvidos: list[dict], informada: str | None) -> str:
    """Base das chaves de idempotência de uma folha executada na hora. Sem chave do app,
    deriva da competência + itens: reenviar a mesma folha (duplo clique, rede ruim) devolve
    os mesmos pagamentos em vez de pagar de novo."""
    if informada:
        return f"folha-{informada}"
    itens = ",".join(f"{r['funcionario_id']}:{r['valor']}" for r in sorted(resolvidos, key=lambda r: r["funcionario_id"]))
    digest = hashlib.sha256(f"{conta['empresa_id']}|{rotulo.strip().lower()}|{itens}".encode()).hexdigest()[:32]
    return f"folha-{digest}"


def pagar(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list,
          descricao: str | None, senha: str | None = None, codigo_totp: str | None = None,
          ip: str | None = None, idempotency_key: str | None = None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, *pagamento_service.PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)
    if not itens:
        raise HTTPException(status_code=400, detail="Folha vazia.")
    resolvidos = _resolver_itens(repo, conta, itens)
    total = sum((Decimal(r["valor"]) for r in resolvidos), Decimal("0"))
    rotulo = descricao or f"Salário {tempo.hoje_brt():%m/%Y}"

    chave = _chave_da_folha(conta, rotulo, resolvidos, idempotency_key)

    def pendente(motivo: str | None) -> dict:
        return {"pendente": pagamento_service.criar_pendente(
            repo, conta=conta, usuario=usuario, tipo="folha", valor=total, ip=ip, motivo=motivo,
            descricao=f"{rotulo} — {len(resolvidos)} funcionário(s)",
            payload={"itens": resolvidos, "descricao": rotulo}, idempotency_key=chave,
        )}

    # R01: a idempotência é resolvida antes da alçada. Reenvio de uma folha que virou
    # pendência devolve a mesma pendência; reenvio de uma folha já paga na hora não
    # recalcula a alçada sobre salários que já saíram (e que já gastaram a alçada).
    carteira = conta["carteira_id"]
    anterior = repo.pendente_por_chave(conta["empresa_id"], f"{carteira}:{chave}")
    if anterior is not None:
        return pendente((anterior["payload"] or {}).get("motivo"))
    ja_pagos = {r["funcionario_id"] for r in resolvidos
                if repo.transacao_por_chave(f"{carteira}:{chave}-f{r['funcionario_id']}") is not None}
    restante = sum((Decimal(r["valor"]) for r in resolvidos if r["funcionario_id"] not in ja_pagos), Decimal("0"))
    motivo = pagamento_service.motivo_aprovacao(repo, conta, usuario, restante) if restante > 0 else None
    if motivo:
        if ja_pagos:
            raise HTTPException(status_code=409, detail="Parte desta folha já foi paga e o restante passa da sua "
                                                        "alçada: lance os demais funcionários numa folha separada.")
        return pendente(motivo)

    verificacao = None
    # Folha confirma por SENHA (reautenticação); +TOTP quando o restante passa do limite.
    if restante > 0:
        seguranca_service.reautenticar_senha(usuario=usuario, senha=senha)
        if restante > pagamento_service._limite_autenticacao_adicional():
            seguranca_service.exigir_totp(repo, usuario=usuario, codigo=codigo_totp)
    return {"resultados": executar(repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=resolvidos,
                                   descricao=rotulo, ip=ip, verificacao=verificacao, auth_metodo=AuthMetodo.SENHA,
                                   chave_base=chave)}


def executar(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list[dict],
             descricao: str, ip: str | None, verificacao: dict | None, chave_base: str | None,
             auth_metodo: AuthMetodo | None = None) -> list[dict]:
    resultados = []
    for it in itens:
        motivo = _motivo_para_nao_pagar(repo, conta, it)
        if motivo:
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "erro", "erro": motivo})
            continue
        destino = repo.buscar_destinatario(it["destino_carteira_id"])
        try:
            r = pagamento_service.transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino,
                valor=Decimal(it["valor"]), descricao=f"{descricao} — {it['nome']}"[:140],
                # Por funcionário, não por posição: reordenar a lista não fura a proteção.
                idempotency_key=f"{chave_base}-f{it['funcionario_id']}" if chave_base else None, ip=ip,
                mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, sem_bloqueio_cautelar=True,
                auth_metodo=auth_metodo,
            )
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "pago",
                               "transacao_id": r["transacao"]["id"]})
        except HTTPException as e:
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "erro", "erro": str(e.detail)})
        except IdempotenciaConflitanteError:
            # R03: um item com chave em conflito não interrompe os demais.
            resultados.append({"funcionario_id": it["funcionario_id"], "situacao": "erro",
                               "erro": "Esta chave de idempotência já foi usada em outra operação."})
    _log(repo, usuario, conta, "folha_paga", ip, itens=len(itens),
         pagos=sum(1 for r in resultados if r["situacao"] == "pago"))
    return resultados
