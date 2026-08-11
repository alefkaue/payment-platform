from fastapi import APIRouter, Depends

from app.repositories.memoria_repository import MemoriaRepository, get_repository
from app.schemas.usuario import LoginCreate, UsuarioCreate, UsuarioResponse
from app.services.usuario_service import (
    criar_usuario as criar_usuario_service,
    login_basico,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioResponse)
def criar_usuario(
    dados: UsuarioCreate, repo: MemoriaRepository = Depends(get_repository)
):
    return criar_usuario_service(
        repo,
        nome=dados.nome,
        carteira_id=dados.carteira_id,
        saldo_inicial=dados.saldo_inicial,
    )


@router.post("/login", response_model=UsuarioResponse)
def login(
    dados: LoginCreate, repo: MemoriaRepository = Depends(get_repository)
):
    return login_basico(repo, dados.carteira_id)


@router.get("", response_model=list[UsuarioResponse])
def listar_usuarios(repo: MemoriaRepository = Depends(get_repository)):
    return repo.listar_usuarios()


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def obter_usuario(
    usuario_id: int, repo: MemoriaRepository = Depends(get_repository)
):
    usuario = repo.obter_usuario(usuario_id)
    if not usuario:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Carteira não encontrada.")
    return usuario
