from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.deps import conta_atual, dispositivo_atual, get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.comum import PendenteResponse, TransacaoResponse
from app.schemas.pagamentos import (
    ContestacaoCreate,
    DecisaoPendente,
    LoteCreate,
    LoteItemResultado,
    TransferenciaCreate,
)
from app.core.config import get_settings
from pydantic import BaseModel, Field
from app.services import pagamento_service, pix_service, split_service

router = APIRouter(prefix="/pagamentos", tags=["pagamentos"])


def resposta_pendente(p: dict) -> JSONResponse:
    corpo = PendenteResponse(operacao_id=p["id"], valor=p["valor"],
                             mensagem="Valor acima da sua alçada: a operação espera aprovação de outra pessoa da empresa.")
    return JSONResponse(status_code=202, content=corpo.model_dump(mode="json"))


@router.post("/transferir", response_model=TransacaoResponse,
             responses={202: {"model": PendenteResponse, "description": "PJ: acima da alçada, aguardando aprovação"}})
def transferir(
    dados: TransferenciaCreate,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    dispositivo: dict | None = Depends(dispositivo_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """Transferência (Pix/TED interno). Nunca retém imposto: split só em cobrança com NF-e."""
    destino = pix_service.resolver_destino(repo, dados.destino)
    r = pagamento_service.transferir(
        repo, usuario=usuario, conta=conta, dispositivo=dispositivo, destino=destino, valor=dados.valor,
        descricao=dados.descricao, biometria=dados.biometria, idempotency_key=dados.idempotency_key, ip=ip,
    )
    return resposta_pendente(r["pendente"]) if "pendente" in r else r["transacao"]


@router.post("/lote", response_model=list[LoteItemResultado])
def transferir_lote(
    dados: LoteCreate,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    dispositivo: dict | None = Depends(dispositivo_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """Até 100 transferências. Cada item tem resultado próprio (um erro não para os outros)."""
    return pagamento_service.transferir_lote(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                             itens=dados.itens, biometria=dados.biometria, ip=ip)


@router.get("/transacoes", response_model=list[TransacaoResponse])
def extrato(
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return repo.listar_transacoes(carteira_id=conta["carteira_id"], limite=limite, offset=offset)


@router.get("/transacoes/{transacao_id}", response_model=TransacaoResponse)
def comprovante(transacao_id: int, conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    t = repo.obter_transacao(transacao_id)
    if not t or conta["carteira_id"] not in (t["origem"]["carteira_id"], t["destino"]["carteira_id"]):
        raise HTTPException(status_code=404, detail="Transação não encontrada.")
    return t


@router.post("/transacoes/{transacao_id}/contestar", status_code=201)
def contestar(
    transacao_id: int,
    dados: ContestacaoCreate,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """Pede a devolução de um pagamento (golpe, fraude, erro). Espelha o MED do Pix."""
    return pagamento_service.contestar(repo, usuario=usuario, conta=conta, transacao_id=transacao_id, motivo=dados.motivo, ip=ip)


@router.post("/pendentes/{operacao_id}/decidir")
def decidir_pendente(
    operacao_id: int,
    dados: DecisaoPendente,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    dispositivo: dict | None = Depends(dispositivo_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """PJ: aprova ou rejeita uma operação acima da alçada (precisa ser outra pessoa)."""
    return pagamento_service.decidir_pendente(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                              operacao_id=operacao_id, aprovar=dados.aprovar,
                                              biometria=dados.biometria, ip=ip)


@router.get("/split/simular")
def simular_split(
    valor: Decimal = Query(..., gt=0, max_digits=12, decimal_places=2),
    ano: int | None = Query(default=None, ge=2026, le=2040),
    regime: str = Query(default="padrao"),
):
    """ESTIMATIVA para a calculadora do site/app. O split real usa o imposto da nota."""
    try:
        return split_service.estimar(valor, ano=ano, regime=regime)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/split/transicao")
def tabela_transicao():
    """Alíquotas de CBS e IBS ano a ano (2026-2033). Referências ainda estimadas."""
    return split_service.tabela_transicao()


class DepositoDemoRequest(BaseModel):
    valor: Decimal = Field(..., gt=0, le=Decimal("10000"), decimal_places=2)


@router.post("/depositar-demo", response_model=TransacaoResponse)
def depositar_demo(dados: DepositoDemoRequest, usuario: dict = Depends(usuario_atual),
                   conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                   ip: str | None = Depends(ip_cliente)):
    """Só em demonstração (DEPOSITO_DEMO=1): coloca dinheiro de teste na conta em uso."""
    if not get_settings().deposito_demo:
        raise HTTPException(status_code=403, detail="Depósito de demonstração desligado neste servidor.")
    return pagamento_service.depositar(repo, admin=usuario, destino=conta, valor=dados.valor, ip=ip)
