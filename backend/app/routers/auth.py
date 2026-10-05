from fastapi import APIRouter, Depends, Response

from app.deps import get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(dados: LoginRequest, repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    usuario = auth_service.autenticar(repo, email=dados.email, senha=dados.senha, ip=ip)
    return auth_service.emitir_tokens(repo, usuario)


@router.post("/refresh", response_model=TokenResponse)
def refresh(dados: RefreshRequest, repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return auth_service.renovar(repo, refresh_token=dados.refresh_token, ip=ip)


@router.post("/logout", status_code=204)
def logout(dados: RefreshRequest, repo: Repositorio = Depends(get_repo)):
    auth_service.logout(repo, refresh_token=dados.refresh_token)
    return Response(status_code=204)


@router.get("/eu")
def eu(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Dados da própria conta (inclui saldo)."""
    conta = repo.obter_carteira_do_usuario(usuario["id"])
    return conta or {"usuario_id": usuario["id"], "email": usuario["email"], "papel": usuario["papel"]}
