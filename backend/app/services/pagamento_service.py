"""
Transferências, lote, aprovação de operações PJ, contestação (MED) e depósito.

Transferência NUNCA tem split: não é operação tributada (Pix de sócio para a
empresa, reembolso, empréstimo...). O split só acontece no pagamento de cobrança
com NF-e -- ver cobranca_service.

Ordem das checagens numa transferência (as baratas primeiro):
1. destino != origem, papel do vínculo (PJ), aparelho informado;
2. alçada (PJ): acima da alçada por operação, da alçada DIÁRIA de quem lança ou
   do limite de assinatura conjunta da Grande, vira operação pendente de aprovação
   (a soma do dia é conferida de novo dentro do lock, ver _checar_alcada_diaria);
3. MFA facial acima de LIMITE_FACIAL_REAIS (prova com desafio do servidor);
4. risco: bloqueio cautelar para destino novo a partir de RISCO_VALOR_MINIMO;
5. saldo + limites (por transação, diurno/noturno, aparelho novo) DENTRO do
   lock da carteira, junto com o débito.

Idempotência: a chave enviada pelo cliente vale por conta de origem (prefixo
`<carteira_id>:`). Antes era global -- outra pessoa que repetisse a mesma chave
recebia de volta a transação de quem usou primeiro. O reenvio é resolvido ANTES da
alçada (R01): se a chave já gerou um pagamento ou uma pendência, devolve o mesmo
resultado em vez de recalcular a alçada (que o pagamento original já consumiu) e
abrir uma segunda operação.
"""

import hashlib
import json
import logging
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.db.models import AuthMetodo, PapelVinculo
from app.deps import chave_do_cliente, exigir_papel, exigir_pj
from app.repositories.exceptions import IdempotenciaConflitanteError, SaldoInsuficienteError
from app.repositories.repository import Repositorio
from app.services import pix_service, seguranca_service, webhook_service
from app.services.split_service import sem_split

logger = logging.getLogger("payflow.pagamento")

PODE_MOVIMENTAR = (PapelVinculo.ADMIN, PapelVinculo.APROVADOR, PapelVinculo.OPERADOR)


def _limite_facial() -> Decimal:
    return Decimal(str(get_settings().limite_facial_reais))


def _limite_autenticacao_adicional() -> Decimal:
    """Acima deste valor o pagamento exige 2º fator (TOTP) além da senha."""
    return get_settings().limite_autenticacao_adicional


def chave_idempotencia(conta: dict, chave: str | None) -> str | None:
    return f"{conta['carteira_id']}:{chave}" if chave else None


_CHAVE_CONFLITANTE = "Esta chave de idempotência já foi usada em outra operação."


def _feita_com_a_chave(repo: Repositorio, conta: dict, chave: str | None, *, mesma) -> dict | None:
    """R01: o que esta chave já produziu, antes de decidir entre executar e pedir aprovação.
    {"transacao": ...} se já virou movimento (conferido por `mesma(transacao)`; outro
    pedido com a mesma chave é 409), {"pendente": ...} se virou pendência (o payload é
    conferido em criar_pendente), None se é a primeira vez."""
    if not chave:
        return None
    t = repo.transacao_por_chave(chave)
    if t is not None:
        if t["origem"]["carteira_id"] != conta["carteira_id"] or not mesma(t):
            raise HTTPException(status_code=409, detail=_CHAVE_CONFLITANTE)
        return {"transacao": t}
    if conta.get("empresa_id") is not None:
        p = repo.pendente_por_chave(conta["empresa_id"], chave)
        if p is not None:
            return {"pendente": p}
    return None


class AlcadaDiariaExcedida(Exception):
    """Levantada dentro do lock da carteira: a soma do dia passou da alçada diária."""


def _alcada_diaria(conta: dict) -> Decimal | None:
    """Teto diário sem aprovação de quem está operando. None = sem limite (PF, admin,
    alçada vazia)."""
    v = conta.get("vinculo")
    if not v or v["alcada"] is None:
        return None
    return v.get("alcada_diaria") if v.get("alcada_diaria") is not None else v["alcada"]


def _assina(conta: dict, valor: Decimal) -> bool:
    """Quem lança conta como uma das assinaturas se tem poder de aprovar este valor."""
    v = conta.get("vinculo")
    return bool(v and v["papel"] in (PapelVinculo.ADMIN.value, PapelVinculo.APROVADOR.value)
                and (v["alcada"] is None or valor <= v["alcada"]))


def motivo_aprovacao(repo: Repositorio, conta: dict, usuario: dict, valor: Decimal) -> str | None:
    """Por que esta operação PJ precisa de outra pessoa (ou None se não precisa).

    1. acima da alçada por operação de quem lança;
    2. a soma do dia de quem lança passaria da alçada diária (fracionamento);
    3. Grande empresa, valor >= LIMITE_DUAS_APROVACOES_REAIS: assinatura conjunta --
       vale também para admin e aprovador sem alçada (antes eles pagavam sozinhos)."""
    from app.services import politica_pj

    v = conta.get("vinculo")
    if conta.get("titular_tipo") != "PJ" or not v:
        return None
    valor = Decimal(valor)
    if v["alcada"] is not None and valor > v["alcada"]:
        return "acima_da_alcada"
    teto = _alcada_diaria(conta)
    if teto is not None and repo.saidas_do_usuario_hoje(conta["carteira_id"], usuario["id"]) + valor > teto:
        return "alcada_diaria"
    porte = repo.obter_empresa(conta["empresa_id"])["porte"]
    if politica_pj.aprovacoes_necessarias(porte, valor) > 1:
        return "assinatura_conjunta"
    return None


def _checar_alcada_diaria(conta: dict, usuario: dict, valor: Decimal, checar_limites):
    """Envolve o checador de limites: dentro do lock, confere de novo a soma do dia de
    quem lança (duas requisições simultâneas não passam juntas do teto)."""
    teto = _alcada_diaria(conta)

    def checar(sessao, origem) -> None:
        if teto is not None:
            usado = Repositorio.soma_saidas_do_usuario(sessao, origem.id, usuario["id"],
                                                       tempo.inicio_do_dia(tempo.agora()))
            if usado + valor > teto:
                raise AlcadaDiariaExcedida()
        if checar_limites is not None:
            checar_limites(sessao, origem)

    return checar


def criar_pendente(repo: Repositorio, *, conta: dict, usuario: dict, tipo: str, valor: Decimal, payload: dict,
                   ip: str | None, descricao: str | None = None, motivo: str | None = None,
                   idempotency_key: str | None = None) -> dict:
    """Operação que precisa de OUTRA pessoa. Quantas aprovações: a política do porte
    (2 na Grande acima do limite), menos 1 se quem lançou já assina por este valor."""
    from app.services import politica_pj

    porte = repo.obter_empresa(conta["empresa_id"])["porte"]
    if tipo == "acesso":
        necessarias = 1
    else:
        necessarias = politica_pj.aprovacoes_necessarias(porte, Decimal(valor))
        if _assina(conta, Decimal(valor)):
            necessarias = max(1, necessarias - 1)
    try:
        p = repo.criar_pendente(empresa_id=conta["empresa_id"], tipo=tipo, valor=valor,
                                payload={**payload, "motivo": motivo} if motivo else payload,
                                criado_por=usuario["id"], descricao=descricao, aprovacoes_necessarias=necessarias,
                                idempotency_key=f"{conta['carteira_id']}:{idempotency_key}" if idempotency_key else None)
    except IdempotenciaConflitanteError:
        raise HTTPException(status_code=409, detail=_CHAVE_CONFLITANTE) from None
    if p.pop("_repetida", False):
        p.pop("_entregas", None)
        return p  # reenvio: a mesma pendência, sem novo aviso nem nova trilha
    repo.registrar_log(ator=usuario["email"], acao="operacao_pendente", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta["empresa_id"],
                       detalhe={"operacao_id": p["id"], "tipo": tipo, "valor": str(valor), "motivo": motivo,
                                "aprovacoes_necessarias": necessarias})
    webhook_service.entregar_agora(repo, p.pop("_entregas", None))
    return p


def transferir(
    repo: Repositorio,
    *,
    usuario: dict,
    conta: dict,
    dispositivo: dict | None,
    destino: dict,
    valor: Decimal,
    descricao: str | None,
    biometria=None,
    senha: str | None = None,
    codigo_totp: str | None = None,
    idempotency_key: str | None = None,
    ip: str | None = None,
    mfa_resolvido: bool = False,
    verificacao_previa: dict | None = None,
    pular_alcada: bool = False,
    auth_metodo: AuthMetodo | None = None,
    sem_bloqueio_cautelar: bool = False,
) -> dict:
    """Devolve {"transacao": ...} ou {"pendente": ...}.

    sem_bloqueio_cautelar: só a folha usa -- o destino é a conta do próprio
    funcionário, resolvida pelo CPF no servidor, então não é "destino novo de risco"."""
    valor = Decimal(valor)
    if destino["carteira_id"] == conta["carteira_id"]:
        raise HTTPException(status_code=400, detail="Não é possível transferir para a própria conta.")
    exigir_papel(conta, *PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)

    def pendente(motivo: str) -> dict:
        return {"pendente": criar_pendente(
            repo, conta=conta, usuario=usuario, tipo="transferencia", valor=valor, ip=ip, motivo=motivo,
            descricao=f"Pix para {destino.get('nome') or 'conta'}"[:200], payload={
                "destino_carteira_id": destino["carteira_id"], "valor": str(valor), "descricao": descricao,
                "idempotency_key": idempotency_key,
            }, idempotency_key=idempotency_key)}

    if not pular_alcada:
        anterior = _feita_com_a_chave(
            repo, conta, chave_idempotencia(conta, idempotency_key),
            mesma=lambda t: (t["tipo"], t["destino"]["carteira_id"], t["valor_bruto"])
            == ("transferencia", destino["carteira_id"], valor))
        if anterior and "transacao" in anterior:
            return anterior
        if anterior:
            # Mesma pendência (criar_pendente confere o pedido inteiro), sem nova alçada.
            return pendente((anterior["pendente"]["payload"] or {}).get("motivo") or "acima_da_alcada")
        motivo = motivo_aprovacao(repo, conta, usuario, valor)
        if motivo:
            return pendente(motivo)

    verificacao = verificacao_previa
    metodo = auth_metodo or (AuthMetodo.SELFIE if verificacao else AuthMetodo.SENHA)
    if not mfa_resolvido and verificacao is None:
        # Pagamento confirma por SENHA (reautenticação no backend; substitui o facial).
        # Acima de LIMITE_AUTENTICACAO_ADICIONAL exige também um 2º fator (TOTP).
        seguranca_service.reautenticar_senha(usuario=usuario, senha=senha)
        if valor > _limite_autenticacao_adicional():
            seguranca_service.exigir_totp(repo, usuario=usuario, codigo=codigo_totp)
        metodo = auth_metodo or AuthMetodo.SENHA

    bloqueio = None if sem_bloqueio_cautelar else seguranca_service.bloqueio_cautelar(
        repo, origem_id=conta["carteira_id"], destino=destino, valor=valor)
    checar = seguranca_service.checador_de_limites(valor=valor, titular_tipo=conta["titular_tipo"], dispositivo=dispositivo)
    if not pular_alcada:
        checar = _checar_alcada_diaria(conta, usuario, valor, checar)
    try:
        t = repo.executar_movimento(
            origem_id=conta["carteira_id"], destino_id=destino["carteira_id"], split=sem_split(valor),
            tipo="transferencia", auth_metodo=metodo, autor_usuario_id=usuario["id"],
            dispositivo_id=dispositivo["id"] if dispositivo else None, descricao=descricao,
            verificacao_facial=verificacao, idempotency_key=chave_idempotencia(conta, idempotency_key),
            bloqueio_ate=bloqueio,
            checar=checar,
            # Outbox: o aviso "pix.recebido" nasce na mesma transação do dinheiro.
            evento=(lambda tx: (destino["empresa_id"], "pix.recebido", {
                "transacao_id": tx["id"], "valor": tx["liquido"], "pagador": tx["origem"]["nome"],
                "status": tx["status"]})) if destino["titular_tipo"] == "PJ" else None,
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")
    except AlcadaDiariaExcedida:
        return pendente("alcada_diaria")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None

    repo.registrar_log(ator=usuario["email"], acao="transferencia", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta.get("empresa_id"), detalhe={
        "transacao_id": t["id"], "valor": str(valor), "destino": destino["carteira_id"], "auth": metodo.value,
        "status": t["status"],
    })
    webhook_service.entregar_agora(repo, t.pop("_entregas", None))
    return {"transacao": t}


def transferir_lote(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list,
                    senha: str | None, codigo_totp: str | None, ip: str | None) -> list[dict]:
    exigir_papel(conta, *PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)
    total = sum((Decimal(i.valor) for i in itens), Decimal("0"))
    # Uma confirmação (senha + TOTP se o total passar do limite) para o lote inteiro.
    seguranca_service.reautenticar_senha(usuario=usuario, senha=senha)
    if total > _limite_autenticacao_adicional():
        seguranca_service.exigir_totp(repo, usuario=usuario, codigo=codigo_totp)
    verificacao = None

    # Remessa duplicada: o mesmo lote (mesmos itens, na mesma ordem) reenviado no mesmo dia
    # devolve os mesmos pagamentos em vez de pagar de novo -- como os bancos fazem com
    # arquivo de remessa repetido. Item com chave própria usa a dele.
    assinatura = json.dumps([[i.destino.model_dump(mode="json"), str(i.valor), i.descricao] for i in itens],
                            sort_keys=True)
    lote_id = hashlib.sha256(f"{conta['carteira_id']}|{tempo.hoje_brt()}|{assinatura}".encode()).hexdigest()[:32]
    resultados = []
    for indice, item in enumerate(itens):
        try:
            destino = pix_service.resolver_destino(repo, item.destino)
            r = transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino, valor=item.valor,
                descricao=item.descricao, idempotency_key=chave_do_cliente(item.idempotency_key) or f"lote-{lote_id}-{indice}", ip=ip,
                mfa_resolvido=True, verificacao_previa=verificacao,
            )
        except HTTPException as e:
            resultados.append({"indice": indice, "situacao": "erro", "erro": str(e.detail)})
            continue
        except IdempotenciaConflitanteError:
            # R03: antes escapava do laço -- 409 no lote inteiro depois de itens já pagos.
            resultados.append({"indice": indice, "situacao": "erro", "erro": _CHAVE_CONFLITANTE})
            continue
        if "pendente" in r:
            resultados.append({"indice": indice, "situacao": "pendente_aprovacao", "operacao_id": r["pendente"]["id"]})
        else:
            resultados.append({"indice": indice, "situacao": r["transacao"]["status"], "transacao_id": r["transacao"]["id"]})
    return resultados


def expirar_vencidas(repo: Repositorio, empresa_id: int) -> int:
    horas = get_settings().pendente_validade_horas
    return repo.expirar_pendentes(empresa_id, tempo.agora() - timedelta(hours=horas))


_INTERROMPIDA = "A execução foi interrompida antes de mover o dinheiro. Nada foi debitado: lance de novo."


def _bate_com(p: dict, t: dict) -> bool:
    """A transação achada pela chave é mesmo a execução desta pendência? (C2-02: defesa
    em profundidade além do espaço de nomes das chaves.)"""
    # Execução de pendência é sempre gravada como APROVACAO; um Pix comum (inclusive um
    # antigo, gravado antes do prefixo "u:") nunca tem esse método (C3-03).
    if t.get("auth_metodo") != AuthMetodo.APROVACAO.value:
        return False
    if p["tipo"] == "transferencia":
        return (t["valor"] == p["valor"]
                and t["destino_carteira_id"] == p["payload"].get("destino_carteira_id"))
    if p["tipo"] == "pagamento_cobranca":
        return t["valor"] == p["valor"]
    if p["tipo"] == "folha":
        destinos = {i["destino_carteira_id"]: Decimal(i["valor"]) for i in p["payload"].get("itens") or []}
        return destinos.get(t["destino_carteira_id"]) == t["valor"]
    if p["tipo"] == "devolucao":
        # Sem valor no pedido, devolve o que faltava: nunca mais que o valor da pendência.
        return (t["destino_carteira_id"] == p["payload"].get("destino_carteira_id")
                and t["valor"] <= p["valor"])
    return False


def resumo_folha(itens: list[dict], resultados: list[dict]) -> dict:
    """R04: aprovar a folha não é o mesmo que pagar. O resultado guarda cada funcionário
    e quantos salários saíram de fato; nenhum pago = a operação fica "falhou"."""
    pagos = sum(1 for r in resultados if r["situacao"] == "pago")
    return {"resultados": resultados, "executados": pagos, "itens": len(itens),
            "parcial": 0 < pagos < len(itens)}


def conciliar_executando(repo: Repositorio) -> dict:
    """Job: operação aprovada que ficou "executando" (o processo caiu entre a última
    aprovação e a gravação do resultado). NUNCA reexecuta: confere no banco, pela chave
    de idempotência "pendente-{id}", se o movimento aconteceu.
    - achou transação: "aprovada" (o dinheiro saiu), com os ids achados;
    - não achou: "falhou" (nada saiu; quem lançou pode lançar de novo);
    - mudança de acesso não tem transação para conferir: "falhou" pedindo conferência."""
    limite = tempo.agora() - timedelta(minutes=get_settings().pendente_executando_min)
    contagem = {"conciliadas": 0, "aprovadas": 0, "falharam": 0}
    for p in repo.pendentes_executando(limite):
        if p["tipo"] == "acesso":
            status, resultado = "falhou", {"erro": "A execução foi interrompida. Confira o acesso em Equipe e refaça se "
                                                   "precisar.", "conciliada": True}
        else:
            achadas = [t for t in repo.transacoes_da_pendente(p["id"], p["empresa_id"]) if _bate_com(p, t)]
            ids = [t["id"] for t in achadas]
            if not ids:
                status, resultado = "falhou", {"erro": _INTERROMPIDA, "conciliada": True}
            elif p["tipo"] == "folha":
                total = len(p["payload"].get("itens") or [])
                status, resultado = "aprovada", {"transacoes": ids, "executados": len(ids), "itens": total,
                                                 "parcial": len(ids) < total,
                                                 "conciliada": True}
            else:
                status, resultado = "aprovada", {"transacao_id": ids[0], "conciliada": True}
        if not repo.reconciliar_pendente(p["id"], status, resultado):
            continue  # alguém concluiu nesse meio-tempo
        contagem["conciliadas"] += 1
        contagem["aprovadas" if status == "aprovada" else "falharam"] += 1
        repo.registrar_log(ator="sistema", acao="operacao_conciliada", empresa_id=p["empresa_id"],
                           detalhe={"operacao_id": p["id"], "status": status, **resultado})
        logger.warning("Operação %s estava executando e foi conciliada como %s.", p["id"], status)
    return contagem


def decidir_pendente(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, operacao_id: int,
                     aprovar: bool, biometria, ip: str | None) -> dict:
    """Maker-checker com N aprovadores. Regras:
    - quem lançou NUNCA aprova (segregação de funções);
    - cada pessoa aprova uma vez; a operação só executa quando atinge
      `aprovacoes_necessarias` (2 na grande empresa acima do limite);
    - pagamento: admin ou aprovador, dentro da própria alçada; mudança de ACESSO:
      só admin;
    - aprovar exige o rosto acima do limite facial (acesso: sempre);
    - vence em PENDENTE_VALIDADE_HORAS (vira "expirada");
    - quem lançou pode CANCELAR (aprovar=False) a própria operação;
    - se quem lançou foi suspenso ou revogado, a operação é cancelada em vez de executada."""
    from app.services import cobranca_service, equipe_service, folha_service  # import tardio (ciclos)

    exigir_pj(conta)
    p = repo.obter_pendente(operacao_id)
    if not p or p["empresa_id"] != conta["empresa_id"]:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    expirar_vencidas(repo, conta["empresa_id"])
    p = repo.obter_pendente(operacao_id)
    if p["status"] == "expirada":
        raise HTTPException(status_code=409, detail="Operação expirou sem decisão. Lance de novo, se ainda fizer sentido.")
    if p["status"] != "pendente":
        raise HTTPException(status_code=409, detail=f"Operação já está '{p['status']}'.")
    log = {"usuario_id": usuario["id"], "empresa_id": conta["empresa_id"]}
    if p["criado_por_usuario_id"] == usuario["id"]:
        if aprovar:
            raise HTTPException(status_code=403, detail="A aprovação precisa ser feita por outra pessoa.")
        if not repo.reservar_pendente(operacao_id, usuario["id"], "cancelada"):
            raise HTTPException(status_code=409, detail="Operação já foi decidida.")
        repo.registrar_log(ator=usuario["email"], acao="operacao_cancelada", ip=ip, detalhe={"operacao_id": operacao_id}, **log)
        return repo.obter_pendente(operacao_id)
    if p["tipo"] == "acesso":
        exigir_papel(conta, PapelVinculo.ADMIN)
    else:
        exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    if p["tipo"] != "acesso" and repo.obter_vinculo(p["criado_por_usuario_id"], conta["empresa_id"]) is None:
        # Quem lançou não tem mais acesso ativo (suspenso/revogado): não executa o que ele pediu.
        repo.reservar_pendente(operacao_id, usuario["id"], "cancelada")
        repo.registrar_log(ator=usuario["email"], acao="operacao_cancelada", ip=ip,
                           detalhe={"operacao_id": operacao_id, "motivo": "autor_sem_acesso"}, **log)
        raise HTTPException(status_code=409, detail="Quem lançou esta operação não tem mais acesso à empresa: ela foi cancelada.")
    if any(a.get("usuario_id") == usuario["id"] for a in p["aprovacoes"]):
        raise HTTPException(status_code=409, detail="Você já aprovou esta operação. Falta outra pessoa.")
    v = conta["vinculo"]
    if p["tipo"] != "acesso" and v["alcada"] is not None and p["valor"] > v["alcada"]:
        raise HTTPException(status_code=403, detail="O valor passa da sua alçada de aprovação.")

    if not aprovar:
        if not repo.reservar_pendente(operacao_id, usuario["id"], "rejeitada"):
            raise HTTPException(status_code=409, detail="Operação já foi decidida.")
        repo.registrar_log(ator=usuario["email"], acao="operacao_rejeitada", ip=ip, detalhe={"operacao_id": operacao_id}, **log)
        return repo.obter_pendente(operacao_id)

    seguranca_service.exigir_dispositivo(dispositivo)
    verificacao = None
    if p["tipo"] == "acesso" or p["valor"] > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="aprovacao")
    situacao = repo.registrar_aprovacao(operacao_id, usuario["id"], usuario["nome"])
    if situacao is None:
        raise HTTPException(status_code=409, detail="Operação já foi decidida.")
    if situacao == "parcial":
        repo.registrar_log(ator=usuario["email"], acao="aprovacao_parcial", ip=ip, detalhe={"operacao_id": operacao_id}, **log)
        return {**repo.obter_pendente(operacao_id), "mensagem": "Aprovação registrada. Falta outra pessoa aprovar."}

    payload = p["payload"]
    try:
        if p["tipo"] == "transferencia":
            destino = repo.buscar_destinatario(payload["destino_carteira_id"])
            r = transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino,
                valor=Decimal(payload["valor"]), descricao=payload.get("descricao"),
                idempotency_key=f"pendente-{operacao_id}", ip=ip, mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, auth_metodo=AuthMetodo.APROVACAO,
            )
            resultado = {"transacao_id": r["transacao"]["id"]}
        elif p["tipo"] == "pagamento_cobranca":
            transacao = cobranca_service.pagar(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, txid=payload["txid"], biometria=None,
                idempotency_key=f"pendente-{operacao_id}", ip=ip, mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, auth_metodo=AuthMetodo.APROVACAO,
            )["transacao"]
            resultado = {"transacao_id": transacao["id"]}
        elif p["tipo"] == "folha":
            resultado = resumo_folha(payload["itens"], folha_service.executar(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=payload["itens"],
                descricao=payload["descricao"], ip=ip, verificacao=verificacao, chave_base=f"pendente-{operacao_id}",
                auth_metodo=AuthMetodo.APROVACAO,
            ))
        elif p["tipo"] == "devolucao":
            r = devolver_pix(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, transacao_id=payload["transacao_id"],
                valor=Decimal(payload["valor"]) if payload.get("valor") is not None else None, biometria=None,
                idempotency_key=f"pendente-{operacao_id}", ip=ip, pular_alcada=True, verificacao_previa=verificacao,
                auth_metodo=AuthMetodo.APROVACAO,
            )
            resultado = {"transacao_id": r["transacao"]["id"]}
        elif p["tipo"] == "acesso":
            vinc = equipe_service.aplicar_aprovacao_acesso(repo, conta=conta, aprovador=usuario, payload=payload, ip=ip)
            resultado = {"vinculo_id": vinc["id"], "status": vinc["status"]}
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de operação desconhecido: {p['tipo']}.")
    except HTTPException as e:
        repo.concluir_pendente(operacao_id, "falhou", {"erro": str(e.detail)})
        raise
    # Folha em que nenhum salário saiu não aparece como "aprovada" (R04).
    status = "falhou" if p["tipo"] == "folha" and not resultado["executados"] else "aprovada"
    repo.concluir_pendente(operacao_id, status, resultado)
    repo.registrar_log(ator=usuario["email"], acao="operacao_aprovada" if status == "aprovada" else "operacao_falhou",
                       ip=ip, detalhe={"operacao_id": operacao_id, "tipo": p["tipo"], **resultado}, **log)
    return repo.obter_pendente(operacao_id)


def repetir_pendente(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, operacao_id: int,
                     biometria, ip: str | None) -> dict:
    """R04: repete só os salários que não saíram de uma folha já aprovada (ex.: faltou
    saldo). Mesmas chaves "pendente-{id}-f{funcionario}" da execução original: o que já
    foi pago não paga de novo. Mesmas regras de quem aprova (outra pessoa, papel, alçada,
    aparelho, rosto acima do limite) e o cadastro é conferido de novo (R05)."""
    from app.services import folha_service  # import tardio (ciclo)

    exigir_pj(conta)
    p = repo.obter_pendente(operacao_id)
    if not p or p["empresa_id"] != conta["empresa_id"]:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    if p["tipo"] != "folha":
        raise HTTPException(status_code=400, detail="Só a folha de pagamento pode ser repetida. Nas outras operações, lance de novo.")
    if p["status"] not in ("aprovada", "falhou"):
        raise HTTPException(status_code=409, detail=f"Operação está '{p['status']}' e não pode ser repetida.")
    if p["criado_por_usuario_id"] == usuario["id"]:
        raise HTTPException(status_code=403, detail="A repetição precisa ser feita por quem pode aprovar a folha, não por quem lançou.")
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    v = conta["vinculo"]
    if v["alcada"] is not None and p["valor"] > v["alcada"]:
        raise HTTPException(status_code=403, detail="O valor passa da sua alçada de aprovação.")
    itens = p["payload"].get("itens") or []
    pagas = {t["destino_carteira_id"]: t["id"] for t in repo.transacoes_da_pendente(operacao_id, p["empresa_id"])
             if _bate_com(p, t)}
    faltam = [it for it in itens if it["destino_carteira_id"] not in pagas]
    if not faltam:
        raise HTTPException(status_code=409, detail="Todos os salários desta folha já foram pagos.")
    seguranca_service.exigir_dispositivo(dispositivo)
    verificacao = None
    if sum((Decimal(it["valor"]) for it in faltam), Decimal("0")) > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="aprovacao")
    # Uma repetição por vez; se o processo cair no meio, o job de conciliação fecha a operação.
    if not repo.mudar_status_pendente(operacao_id, p["status"], "executando"):
        raise HTTPException(status_code=409, detail="A operação mudou enquanto você decidia. Atualize a lista.")
    novos = {r["funcionario_id"]: r for r in folha_service.executar(
        repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=faltam,
        descricao=p["payload"]["descricao"], ip=ip, verificacao=verificacao, chave_base=f"pendente-{operacao_id}",
        auth_metodo=AuthMetodo.APROVACAO)}
    resultados = [{"funcionario_id": it["funcionario_id"], "situacao": "pago",
                   "transacao_id": pagas[it["destino_carteira_id"]]}
                  if it["destino_carteira_id"] in pagas else novos[it["funcionario_id"]] for it in itens]
    resultado = {**resumo_folha(itens, resultados), "repeticoes": int((p["resultado"] or {}).get("repeticoes", 0)) + 1}
    status = "aprovada" if resultado["executados"] else "falhou"
    repo.concluir_pendente(operacao_id, status, resultado)
    repo.registrar_log(ator=usuario["email"], acao="operacao_repetida", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta["empresa_id"],
                       detalhe={"operacao_id": operacao_id, "status": status, "executados": resultado["executados"],
                                "itens": resultado["itens"]})
    return repo.obter_pendente(operacao_id)


# =============================================================================
# Contestação (MED) e bloqueio cautelar
# =============================================================================


def devolver_pix(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, transacao_id: int,
                 valor: Decimal | None, biometria, idempotency_key: str | None, ip: str | None,
                 pular_alcada: bool = False, verificacao_previa: dict | None = None,
                 auth_metodo: AuthMetodo | None = None) -> dict:
    """Devolução voluntária: quem recebeu um Pix devolve tudo ou parte (R1-13). Não é MED:
    é decisão do recebedor. Mesmas travas de quem movimenta: papel, aparelho, rosto acima
    do limite facial, idempotência -- e, na PJ, a alçada por operação e diária de quem
    devolve (R02): acima dela, vira operação pendente de aprovação.

    Devolve {"transacao": ...} ou {"pendente": ...}. Sem `valor`, a alçada é conferida
    sobre o valor recebido (teto do que pode ser devolvido)."""
    exigir_papel(conta, *PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)
    t = repo.obter_transacao(transacao_id)
    if not t or t["destino"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Transação não encontrada nesta conta.")
    teto = Decimal(valor) if valor is not None else t["liquido"]
    chave = chave_idempotencia(conta, idempotency_key)

    def pendente(motivo: str) -> dict:
        return {"pendente": criar_pendente(
            repo, conta=conta, usuario=usuario, tipo="devolucao", valor=teto, ip=ip, motivo=motivo,
            descricao=f"Devolução de Pix para {t['origem'].get('nome') or 'pagador'}"[:200], payload={
                "transacao_id": transacao_id, "valor": str(valor) if valor is not None else None,
                "destino_carteira_id": t["origem"]["carteira_id"], "idempotency_key": idempotency_key,
            }, idempotency_key=idempotency_key)}

    checar = None
    if not pular_alcada:
        anterior = _feita_com_a_chave(
            repo, conta, chave,
            mesma=lambda d: d["tipo"] == "devolucao" and d["transacao_original_id"] == transacao_id
            and (valor is None or d["valor_bruto"] == Decimal(valor)))
        if anterior and "transacao" in anterior:
            return anterior
        if anterior:
            return pendente((anterior["pendente"]["payload"] or {}).get("motivo") or "acima_da_alcada")
        motivo = motivo_aprovacao(repo, conta, usuario, teto)
        if motivo:
            return pendente(motivo)
        checar = _checar_alcada_diaria(conta, usuario, teto, None)

    verificacao = verificacao_previa
    metodo = auth_metodo or (AuthMetodo.SELFIE if verificacao else AuthMetodo.SENHA)
    if verificacao is None and not pular_alcada and teto > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="devolucao")
        metodo = auth_metodo or AuthMetodo.SELFIE
    try:
        dev = repo.devolver_voluntario(
            transacao_id=transacao_id, recebedor_carteira_id=conta["carteira_id"],
            valor=Decimal(valor) if valor is not None else None, autor_usuario_id=usuario["id"], auth_metodo=metodo,
            idempotency_key=chave, verificacao_facial=verificacao,
            prazo_dias=get_settings().devolucao_prazo_dias, checar=checar)
    except AlcadaDiariaExcedida:
        return pendente("alcada_diaria")
    except LookupError:
        raise HTTPException(status_code=404, detail="Transação não encontrada nesta conta.") from None
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para devolver.") from None
    except IdempotenciaConflitanteError:
        raise HTTPException(status_code=409, detail="Esta chave de idempotência já foi usada em outra operação.") from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    repo.registrar_log(ator=usuario["email"], acao="pix_devolvido", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta.get("empresa_id"),
                       detalhe={"transacao_id": transacao_id, "devolucao_id": dev["id"], "valor": str(dev["valor_bruto"])})
    return {"transacao": dev}


def contestar(repo: Repositorio, *, usuario: dict, conta: dict, transacao_id: int, motivo: str, ip: str | None) -> dict:
    t = repo.obter_transacao(transacao_id)
    if not t or t["origem"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Transação não encontrada nesta conta.")
    exigir_papel(conta, PapelVinculo.ADMIN)
    if t["tipo"] not in ("transferencia", "cobranca"):
        raise HTTPException(status_code=400, detail="Só transferências e pagamentos podem ser contestados.")
    if t["status"] not in ("concluida", "retida"):
        raise HTTPException(status_code=400, detail=f"Transação com status '{t['status']}' não pode ser contestada.")
    if tempo.agora() - t["data_hora"] > timedelta(days=get_settings().contestacao_prazo_dias):
        raise HTTPException(status_code=400, detail="Prazo de contestação encerrado.")
    c = repo.criar_contestacao(transacao_id=transacao_id, usuario_id=usuario["id"], motivo=motivo)
    if c is None:
        raise HTTPException(status_code=409, detail="Esta transação já tem uma contestação.")
    repo.registrar_log(ator=usuario["email"], acao="contestacao_aberta", ip=ip, usuario_id=usuario["id"], empresa_id=conta.get("empresa_id"), detalhe={"transacao_id": transacao_id})
    return c


def decidir_contestacao(repo: Repositorio, *, admin: dict, contestacao_id: int, procedente: bool, ip: str | None) -> dict:
    c = repo.obter_contestacao(contestacao_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contestação não encontrada.")
    if c["status"] != "aberta":
        raise HTTPException(status_code=409, detail="Contestação já decidida.")
    resultado = repo.resolver_contestacao(contestacao_id, procedente=procedente, autor_usuario_id=admin["id"])
    if resultado is None:
        raise HTTPException(status_code=409, detail="Contestação já decidida.")
    devolvido = resultado["valor_devolvido"]
    repo.registrar_log(ator=admin["email"], acao="contestacao_decidida", ip=ip,
                       detalhe={"contestacao_id": contestacao_id, "procedente": procedente, "devolvido": str(devolvido)})
    return resultado


def liberar_bloqueios_vencidos(repo: Repositorio) -> dict:
    ids = repo.transacoes_retidas_vencidas(tempo.agora())
    for i in ids:
        repo.liberar_bloqueio(i)
    return {"liberadas": len(ids)}


# =============================================================================
# Depósito (admin) -- sai da conta CAIXA
# =============================================================================


def depositar(repo: Repositorio, *, admin: dict, destino: dict, valor: Decimal, ip: str | None,
              idempotency_key: str | None = None) -> dict:
    caixa = repo.carteira_sistema("CAIXA")
    try:
        t = repo.executar_movimento(
            origem_id=caixa["carteira_id"], destino_id=destino["carteira_id"], split=sem_split(valor), tipo="deposito",
            auth_metodo=AuthMetodo.SISTEMA, autor_usuario_id=admin["id"], permitir_saldo_negativo=True,
            descricao="Depósito", idempotency_key=f"deposito:{destino['carteira_id']}:{idempotency_key}" if idempotency_key else None,
        )
    except IdempotenciaConflitanteError:
        raise HTTPException(status_code=409, detail="Esta chave de idempotência já foi usada em outro depósito.") from None
    repo.registrar_log(ator=admin["email"], acao="deposito", ip=ip,
                       detalhe={"carteira_id": destino["carteira_id"], "valor": str(valor), "transacao_id": t["id"]})
    return t
