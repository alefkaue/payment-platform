from fastapi import APIRouter, Depends
from app.repositories.memoria_repository import MemoriaRepository, get_repository
from app.schemas.transacao import TransacaoCreate, TransacaoResponse
from app.services.pagamento_service import realizar_transferencia

router = APIRouter(prefix="/pagamentos", tags=["pagamentos"])


@router.post("/transferir", response_model=TransacaoResponse)
def transferir(
    dados: TransacaoCreate, repo: MemoriaRepository = Depends(get_repository)
):
    return realizar_transferencia(
        repo,
        origem_id=dados.origem_usuario_id,
        destino_id=dados.destino_usuario_id,
        valor=dados.valor,
    )


@router.get("/transacoes", response_model=list[TransacaoResponse])
def listar_transacoes(repo: MemoriaRepository = Depends(get_repository)):
    return repo.listar_transacoes()
