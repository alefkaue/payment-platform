"""Administração e jobs. Em produção os jobs rodam por agendador (cron do
Container Apps / Azure Functions) chamando estes endpoints com um token admin."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import admin_atual, get_repo, ip_cliente
from app.repositories.repository import Repositorio
from app.schemas.comum import ContaResponse, TransacaoResponse
from app.schemas.pagamentos import DecisaoContestacao, DepositoRequest
from app.services import (
    cobranca_service,
    pagamento_service,
    pix_service,
    rendimento_service,
    tributos_service,
    webhook_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/kyc/casos")
def casos_kyc(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
              status: str = Query(default="em_analise", pattern="^(em_analise|aprovado|reprovado)$")):
    """Fila de análise humana: documentos que a máquina não conseguiu conferir sozinha."""
    return repo.listar_casos_kyc(status)


@router.post("/kyc/casos/{caso_id}/decidir")
def decidir_kyc(caso_id: int, aprovar: bool = Query(...), admin: dict = Depends(admin_atual),
                repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    c = repo.decidir_caso_kyc(caso_id, "aprovado" if aprovar else "reprovado")
    if c is None:
        raise HTTPException(status_code=409, detail="Caso não encontrado ou já decidido.")
    repo.registrar_log(ator=admin["email"], acao="kyc_decidido", ip=ip, usuario_id=admin["id"],
                       detalhe={"caso_id": caso_id, "aprovado": aprovar})
    return c


@router.post("/depositar", response_model=TransacaoResponse)
def depositar(dados: DepositoRequest, admin: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
              ip: str | None = Depends(ip_cliente)):
    """Credita uma conta a partir do CAIXA (simula a entrada de dinheiro de fora)."""
    destino = pix_service.resolver_destino(repo, dados.destino)
    return pagamento_service.depositar(repo, admin=admin, destino=destino, valor=dados.valor, ip=ip)


@router.get("/contas", response_model=list[ContaResponse])
def listar_contas(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
                  limite: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return repo.listar_contas(limite=limite, offset=offset)


@router.get("/transacoes", response_model=list[TransacaoResponse])
def todas_transacoes(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
                     limite: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return repo.listar_transacoes(limite=limite, offset=offset)


@router.post("/transacoes/{transacao_id}/liberar", response_model=TransacaoResponse)
def liberar_bloqueio(transacao_id: int, admin: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
                     ip: str | None = Depends(ip_cliente)):
    t = repo.liberar_bloqueio(transacao_id)
    if t is None:
        raise HTTPException(status_code=409, detail="Transação não está retida.")
    repo.registrar_log(ator=admin["email"], acao="bloqueio_liberado", ip=ip, detalhe={"transacao_id": transacao_id})
    return t


@router.get("/contestacoes")
def contestacoes(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo), status: str | None = "aberta"):
    return repo.listar_contestacoes(status)


@router.post("/contestacoes/{contestacao_id}/decidir")
def decidir_contestacao(contestacao_id: int, dados: DecisaoContestacao, admin: dict = Depends(admin_atual),
                        repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return pagamento_service.decidir_contestacao(repo, admin=admin, contestacao_id=contestacao_id,
                                                 procedente=dados.procedente, ip=ip)


@router.get("/tributos/resumo")
def resumo_tributos(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    return {**repo.resumo_tributos(), "saldo_conta_tributos": repo.carteira_sistema("TRIBUTOS")["saldo"]}


@router.post("/tributos/repassar")
def repassar_tributos(admin: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo),
                      corte: datetime | None = None, ip: str | None = Depends(ip_cliente)):
    """Leva ao fisco o que foi retido antes do `corte` (padrão: início de hoje = D+1)."""
    r = tributos_service.repassar(repo, corte=corte)
    repo.registrar_log(ator=admin["email"], acao="repasse_tributos", ip=ip, detalhe={"repasse_id": r["id"], "total": str(r["total"])})
    return r


# ------------------------------------------------------------------ jobs


@router.post("/jobs/liberar-bloqueios")
def job_liberar(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    return pagamento_service.liberar_bloqueios_vencidos(repo)


@router.post("/jobs/rendimento")
def job_rendimento(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo), data: date | None = None):
    return rendimento_service.processar(repo, data=data)


@router.post("/jobs/recorrencias")
def job_recorrencias(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    return cobranca_service.processar_recorrencias(repo)


@router.post("/jobs/conciliar-pendentes")
def job_conciliar_pendentes(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    """Operações aprovadas que ficaram "executando" (queda no meio): confere no banco se o
    dinheiro saiu e fecha como aprovada ou falhou. Nunca reexecuta."""
    return pagamento_service.conciliar_executando(repo)


@router.post("/jobs/webhooks")
def job_webhooks(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    return webhook_service.processar_pendentes(repo)
