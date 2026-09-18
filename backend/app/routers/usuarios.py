from fastapi import APIRouter, Depends

from app.repositories.memoria_repository import MemoriaRepository, get_repository
from app.schemas.usuario import UsuarioCreate, UsuarioResponse
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioResponse, status_code=201)
def criar_usuario(
    dados: UsuarioCreate, repo: MemoriaRepository = Depends(get_repository)
):
    return usuario_service.criar_usuario(
        repo,
        carteira_id=dados.carteira_id,
        nome=dados.nome,
        foto_rosto_base64=dados.foto_rosto_base64,
        saldo_inicial=dados.saldo_inicial,
    )


@router.get("", response_model=list[UsuarioResponse])
def listar_usuarios(repo: MemoriaRepository = Depends(get_repository)):
    return usuario_service.listar_usuarios(repo)


@router.get("/{carteira_id}", response_model=UsuarioResponse)
def obter_usuario(
    carteira_id: int, repo: MemoriaRepository = Depends(get_repository)
):
    return usuario_service.obter_usuario_ou_404(repo, carteira_id)
