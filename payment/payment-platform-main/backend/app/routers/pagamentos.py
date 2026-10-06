from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.models import TipoPessoa
from app.deps import get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.transacao import TransacaoResponse, TransferenciaCreate
from app.services import pagamento_service, split_service

router = APIRouter(prefix="/pagamentos", tags=["pagamentos"])


@router.post("/transferir", response_model=TransacaoResponse)
def transferir(
    dados: TransferenciaCreate,
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    # A origem é SEMPRE a carteira do usuário autenticado -- não vem do corpo da
    # requisição (não dá pra forjar origem de outra pessoa).
    minha = repo.obter_carteira_do_usuario(usuario["id"])
    if not minha:
        raise HTTPException(status_code=400, detail="Sua conta não tem carteira.")
    return pagamento_service.realizar_transferencia(
        repo,
        usuario=usuario,
        origem_carteira_id=minha["carteira_id"],
        destino_carteira_id=dados.destino_carteira_id,
        valor=dados.valor,
        foto_verificacao_base64=dados.foto_verificacao_base64,
        idempotency_key=dados.idempotency_key,
        ip=ip,
    )


@router.get("/transacoes", response_model=list[TransacaoResponse])
def listar_transacoes(
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return pagamento_service.listar_transacoes(repo, usuario=usuario, limite=limite, offset=offset)


@router.get("/split/simular")
def simular_split(
    valor: Decimal = Query(..., gt=0, description="Valor bruto (reais)."),
    tipo_destino: TipoPessoa = Query(default=TipoPessoa.PJ),
):
    """Prévia do split (calculadora do site/app) -- público, não toca saldo."""
    return split_service.calcular_split(valor, tipo_destino).para_dict()
