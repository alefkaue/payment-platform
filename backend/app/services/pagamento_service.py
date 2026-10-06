"""
Transferências, lote, aprovação de operações PJ, contestação (MED) e depósito.

Transferência NUNCA tem split: não é operação tributada (Pix de sócio para a
empresa, reembolso, empréstimo...). O split só acontece no pagamento de cobrança
com NF-e -- ver cobranca_service.

Ordem das checagens numa transferência (as baratas primeiro):
1. destino != origem, papel do vínculo (PJ), aparelho informado;
2. alçada (PJ): acima dela vira operação pendente de aprovação;
3. MFA facial acima de LIMITE_FACIAL_REAIS (prova com desafio do servidor);
4. risco: bloqueio cautelar para destino novo a partir de RISCO_VALOR_MINIMO;
5. saldo + limites (por transação, diurno/noturno, aparelho novo) DENTRO do
   lock da carteira, junto com o débito.

Idempotência: a chave enviada pelo cliente vale por conta de origem (prefixo
`<carteira_id>:`). Antes era global -- outra pessoa que repetisse a mesma chave
recebia de volta a transação de quem usou primeiro.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.db.models import AuthMetodo, PapelVinculo
from app.deps import exigir_papel, exigir_pj
from app.repositories.exceptions import SaldoInsuficienteError
from app.repositories.repository import Repositorio
from app.services import pix_service, seguranca_service, webhook_service
from app.services.split_service import sem_split

logger = logging.getLogger("payflow.pagamento")

PODE_MOVIMENTAR = (PapelVinculo.ADMIN, PapelVinculo.APROVADOR, PapelVinculo.OPERADOR)


def _limite_facial() -> Decimal:
    return Decimal(str(get_settings().limite_facial_reais))


def chave_idempotencia(conta: dict, chave: str | None) -> str | None:
    return f"{conta['carteira_id']}:{chave}" if chave else None


def precisa_aprovacao(conta: dict, valor: Decimal) -> bool:
    v = conta.get("vinculo")
    return bool(v and v["alcada"] is not None and valor > v["alcada"])


def criar_pendente(repo: Repositorio, *, conta: dict, usuario: dict, tipo: str, valor: Decimal, payload: dict, ip: str | None) -> dict:
    p = repo.criar_pendente(empresa_id=conta["empresa_id"], tipo=tipo, valor=valor, payload=payload, criado_por=usuario["id"])
    repo.registrar_log(ator=usuario["email"], acao="operacao_pendente", ip=ip, detalhe={"operacao_id": p["id"], "valor": str(valor)})
    webhook_service.emitir(repo, empresa_id=conta["empresa_id"], evento="operacao.pendente",
                           payload={"operacao_id": p["id"], "tipo": tipo, "valor": valor})
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
    idempotency_key: str | None = None,
    ip: str | None = None,
    mfa_resolvido: bool = False,
    verificacao_previa: dict | None = None,
    pular_alcada: bool = False,
    auth_metodo: AuthMetodo | None = None,
) -> dict:
    """Devolve {"transacao": ...} ou {"pendente": ...}."""
    valor = Decimal(valor)
    if destino["carteira_id"] == conta["carteira_id"]:
        raise HTTPException(status_code=400, detail="Não é possível transferir para a própria conta.")
    exigir_papel(conta, *PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)

    if not pular_alcada and precisa_aprovacao(conta, valor):
        p = criar_pendente(repo, conta=conta, usuario=usuario, tipo="transferencia", valor=valor, ip=ip, payload={
            "destino_carteira_id": destino["carteira_id"], "valor": str(valor), "descricao": descricao,
            "idempotency_key": idempotency_key,
        })
        return {"pendente": p}

    verificacao = verificacao_previa
    metodo = auth_metodo or (AuthMetodo.SELFIE if verificacao else AuthMetodo.SENHA)
    if not mfa_resolvido and verificacao is None and valor > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="transferencia")
        metodo = auth_metodo or AuthMetodo.SELFIE

    bloqueio = seguranca_service.bloqueio_cautelar(repo, origem_id=conta["carteira_id"], destino=destino, valor=valor)
    try:
        t = repo.executar_movimento(
            origem_id=conta["carteira_id"], destino_id=destino["carteira_id"], split=sem_split(valor),
            tipo="transferencia", auth_metodo=metodo, autor_usuario_id=usuario["id"],
            dispositivo_id=dispositivo["id"] if dispositivo else None, descricao=descricao,
            verificacao_facial=verificacao, idempotency_key=chave_idempotencia(conta, idempotency_key),
            bloqueio_ate=bloqueio,
            checar=seguranca_service.checador_de_limites(valor=valor, titular_tipo=conta["titular_tipo"], dispositivo=dispositivo),
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")

    repo.registrar_log(ator=usuario["email"], acao="transferencia", ip=ip, detalhe={
        "transacao_id": t["id"], "valor": str(valor), "destino": destino["carteira_id"], "auth": metodo.value,
        "status": t["status"],
    })
    if destino["titular_tipo"] == "PJ":
        webhook_service.emitir(repo, empresa_id=destino["empresa_id"], evento="pix.recebido", payload={
            "transacao_id": t["id"], "valor": t["liquido"], "pagador": t["origem"]["nome"], "status": t["status"],
        })
    return {"transacao": t}


def transferir_lote(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, itens: list, biometria, ip: str | None) -> list[dict]:
    exigir_papel(conta, *PODE_MOVIMENTAR)
    seguranca_service.exigir_dispositivo(dispositivo)
    total = sum((Decimal(i.valor) for i in itens), Decimal("0"))
    verificacao = None
    if total > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="lote")

    resultados = []
    for indice, item in enumerate(itens):
        try:
            destino = pix_service.resolver_destino(repo, item.destino)
            r = transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino, valor=item.valor,
                descricao=item.descricao, idempotency_key=item.idempotency_key, ip=ip,
                mfa_resolvido=True, verificacao_previa=verificacao,
            )
        except HTTPException as e:
            resultados.append({"indice": indice, "situacao": "erro", "erro": str(e.detail)})
            continue
        if "pendente" in r:
            resultados.append({"indice": indice, "situacao": "pendente_aprovacao", "operacao_id": r["pendente"]["id"]})
        else:
            resultados.append({"indice": indice, "situacao": r["transacao"]["status"], "transacao_id": r["transacao"]["id"]})
    return resultados


def decidir_pendente(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, operacao_id: int,
                     aprovar: bool, biometria, ip: str | None) -> dict:
    from app.services import cobranca_service  # import tardio: cobranca_service importa este módulo

    exigir_pj(conta)
    p = repo.obter_pendente(operacao_id)
    if not p or p["empresa_id"] != conta["empresa_id"]:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    if p["status"] != "pendente":
        raise HTTPException(status_code=409, detail=f"Operação já está '{p['status']}'.")
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    if p["criado_por_usuario_id"] == usuario["id"]:
        raise HTTPException(status_code=403, detail="A aprovação precisa ser feita por outra pessoa.")
    v = conta["vinculo"]
    if v["alcada"] is not None and p["valor"] > v["alcada"]:
        raise HTTPException(status_code=403, detail="O valor passa da sua alçada de aprovação.")

    if not aprovar:
        if not repo.reservar_pendente(operacao_id, usuario["id"], "rejeitada"):
            raise HTTPException(status_code=409, detail="Operação já foi decidida.")
        repo.registrar_log(ator=usuario["email"], acao="operacao_rejeitada", ip=ip, detalhe={"operacao_id": operacao_id})
        return repo.obter_pendente(operacao_id)

    seguranca_service.exigir_dispositivo(dispositivo)
    verificacao = None
    if p["valor"] > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="aprovacao")
    if not repo.reservar_pendente(operacao_id, usuario["id"], "aprovada"):
        raise HTTPException(status_code=409, detail="Operação já foi decidida.")

    payload = p["payload"]
    try:
        if p["tipo"] == "transferencia":
            destino = repo.obter_conta(payload["destino_carteira_id"])
            r = transferir(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino,
                valor=Decimal(payload["valor"]), descricao=payload.get("descricao"),
                idempotency_key=f"pendente-{operacao_id}", ip=ip, mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, auth_metodo=AuthMetodo.APROVACAO,
            )
            transacao = r["transacao"]
        else:  # pagamento_cobranca
            transacao = cobranca_service.pagar(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, txid=payload["txid"], biometria=None,
                idempotency_key=f"pendente-{operacao_id}", ip=ip, mfa_resolvido=True,
                verificacao_previa=verificacao, pular_alcada=True, auth_metodo=AuthMetodo.APROVACAO,
            )["transacao"]
    except HTTPException as e:
        repo.concluir_pendente(operacao_id, "falhou", {"erro": str(e.detail)})
        raise
    repo.concluir_pendente(operacao_id, "aprovada", {"transacao_id": transacao["id"]})
    repo.registrar_log(ator=usuario["email"], acao="operacao_aprovada", ip=ip, detalhe={"operacao_id": operacao_id, "transacao_id": transacao["id"]})
    return repo.obter_pendente(operacao_id)


# =============================================================================
# Contestação (MED) e bloqueio cautelar
# =============================================================================


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
    repo.registrar_log(ator=usuario["email"], acao="contestacao_aberta", ip=ip, detalhe={"transacao_id": transacao_id})
    return c


def decidir_contestacao(repo: Repositorio, *, admin: dict, contestacao_id: int, procedente: bool, ip: str | None) -> dict:
    c = repo.obter_contestacao(contestacao_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contestação não encontrada.")
    if c["status"] != "aberta":
        raise HTTPException(status_code=409, detail="Contestação já decidida.")
    t = repo.obter_transacao(c["transacao_id"])
    devolvido = Decimal("0.00")
    if procedente:
        r = repo.devolver(transacao_id=t["id"], valor_maximo=t["liquido"], tipo="devolucao", autor_usuario_id=admin["id"])
        devolvido = r["valor_devolvido"]
    elif t["status"] == "retida":
        repo.liberar_bloqueio(t["id"])
    repo.fechar_contestacao(contestacao_id, status="procedente" if procedente else "improcedente", valor_devolvido=devolvido)
    repo.registrar_log(ator=admin["email"], acao="contestacao_decidida", ip=ip,
                       detalhe={"contestacao_id": contestacao_id, "procedente": procedente, "devolvido": str(devolvido)})
    return repo.obter_contestacao(contestacao_id)


def liberar_bloqueios_vencidos(repo: Repositorio) -> dict:
    ids = repo.transacoes_retidas_vencidas(tempo.agora())
    for i in ids:
        repo.liberar_bloqueio(i)
    return {"liberadas": len(ids)}


# =============================================================================
# Depósito (admin) -- sai da conta CAIXA
# =============================================================================


def depositar(repo: Repositorio, *, admin: dict, destino: dict, valor: Decimal, ip: str | None) -> dict:
    caixa = repo.carteira_sistema("CAIXA")
    t = repo.executar_movimento(
        origem_id=caixa["carteira_id"], destino_id=destino["carteira_id"], split=sem_split(valor), tipo="deposito",
        auth_metodo=AuthMetodo.SISTEMA, autor_usuario_id=admin["id"], permitir_saldo_negativo=True,
        descricao="Depósito",
    )
    repo.registrar_log(ator=admin["email"], acao="deposito", ip=ip,
                       detalhe={"carteira_id": destino["carteira_id"], "valor": str(valor), "transacao_id": t["id"]})
    return t
