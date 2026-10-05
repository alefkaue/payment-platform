"""
Dependências do FastAPI para autenticação e autorização.

- `get_repo`: injeta o repositório único.
- `usuario_atual`: exige um access token JWT válido no header Authorization:
  Bearer <token>; carrega o usuário. Fecha o item #1 (endpoints sem login).
- `admin_atual`: além de autenticado, exige papel admin (ex: depósito, relatórios
  do Governo).
- `ip_cliente`: IP de origem para a auditoria/rate-limit.
"""

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security
from app.db.models import Papel
from app.repositories import get_repository
from app.repositories.repository import Repositorio

_bearer = HTTPBearer(auto_error=False)


def get_repo() -> Repositorio:
    return get_repository()


def ip_cliente(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    repo: Repositorio = Depends(get_repo),
) -> dict:
    if credenciais is None or not credenciais.credentials:
        raise HTTPException(status_code=401, detail="Autenticação necessária.", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = security.decodificar_token(credenciais.credentials, "access")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.", headers={"WWW-Authenticate": "Bearer"})

    usuario = repo.obter_usuario_por_id(int(payload["sub"]))
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa ou inexistente.")
    return usuario


def admin_atual(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["papel"] != Papel.ADMIN.value:
        raise HTTPException(status_code=403, detail="Ação restrita a administradores.")
    return usuario
