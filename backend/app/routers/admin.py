from fastapi import APIRouter, Depends

from app.deps import admin_atual, get_repo, ip_cliente
from app.repositories.repository import Repositorio
from app.schemas.transacao import DepositoRequest, RetencaoGovernoResponse, TransacaoResponse
from app.services import deposito_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/depositar", response_model=TransacaoResponse)
def depositar(
    dados: DepositoRequest,
    admin: dict = Depends(admin_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """Credita saldo numa carteira a partir da conta Governo. Substitui o
    saldo_inicial livre do cadastro (item #2)."""
    return deposito_service.depositar(repo, admin=admin, carteira_id=dados.carteira_id, valor=dados.valor, ip=ip)


@router.get("/governo/retencoes", response_model=RetencaoGovernoResponse)
def retencoes(_: dict = Depends(admin_atual), repo: Repositorio = Depends(get_repo)):
    """Total de IBS/CBS retido e repassado à conta Governo (tela Governo do app)."""
    return repo.total_retido_governo()
