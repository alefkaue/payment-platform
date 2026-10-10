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
                   ip: str | None, descricao: str | None = None, motivo: str | None = None) -> dict:
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
    p = repo.criar_pendente(empresa_id=conta["empresa_id"], tipo=tipo, valor=valor,
                            payload={**payload, "motivo": motivo} if motivo else payload,
                            criado_por=usuario["id"], descricao=descricao, aprovacoes_necessarias=necessarias)
    repo.registrar_log(ator=usuario["email"], acao="operacao_pendente", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta["empresa_id"],
                       detalhe={"operacao_id": p["id"], "tipo": tipo, "valor": str(valor), "motivo": motivo,
                                "aprovacoes_necessarias": necessarias})
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
            })}

    if not pular_alcada:
        motivo = motivo_aprovacao(repo, conta, usuario, valor)
        if motivo:
            return pendente(motivo)

    verificacao = verificacao_previa
    metodo = auth_metodo or (AuthMetodo.SELFIE if verificacao else AuthMetodo.SENHA)
    if not mfa_resolvido and verificacao is None and valor > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="transferencia")
        metodo = auth_metodo or AuthMetodo.SELFIE

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
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")
    except AlcadaDiariaExcedida:
        return pendente("alcada_diaria")

    repo.registrar_log(ator=usuario["email"], acao="transferencia", ip=ip, usuario_id=usuario["id"],
                       empresa_id=conta.get("empresa_id"), detalhe={
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


def expirar_vencidas(repo: Repositorio, empresa_id: int) -> int:
    horas = get_settings().pendente_validade_horas
    return repo.expirar_pendentes(empresa_id, tempo.agora() - timedelta(hours=horas))


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
            destino = repo.obter_conta(payload["destino_carteira_id"])
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
            resultado = {"resultados": folha_service.executar(
                repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=payload["itens"],
                descricao=payload["descricao"], ip=ip, verificacao=verificacao, chave_base=f"pendente-{operacao_id}",
                auth_metodo=AuthMetodo.APROVACAO,
            )}
        elif p["tipo"] == "acesso":
            vinc = equipe_service.aplicar_aprovacao_acesso(repo, conta=conta, aprovador=usuario, payload=payload, ip=ip)
            resultado = {"vinculo_id": vinc["id"], "status": vinc["status"]}
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de operação desconhecido: {p['tipo']}.")
    except HTTPException as e:
        repo.concluir_pendente(operacao_id, "falhou", {"erro": str(e.detail)})
        raise
    repo.concluir_pendente(operacao_id, "aprovada", resultado)
    repo.registrar_log(ator=usuario["email"], acao="operacao_aprovada", ip=ip,
                       detalhe={"operacao_id": operacao_id, "tipo": p["tipo"], **resultado}, **log)
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
