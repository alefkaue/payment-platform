from fastapi import APIRouter, Body, Depends, HTTPException

from app.deps import get_repo, ip_cliente, usuario_opcional
from app.repositories.repository import Repositorio
from app.services import biometria_service

router = APIRouter(prefix="/biometria", tags=["biometria"])

_MAX_DESAFIOS_IP_MIN = 20


@router.post("/desafios", status_code=201)
def novo_desafio(
    usuario: dict | None = Depends(usuario_opcional),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    login: str | None = Body(default=None, embed=True, max_length=180),
    modo: str = Body(default="login", embed=True, max_length=20),
):
    """Gera o desafio de prova de vida (ação + validade). Logado, o desafio fica
    preso à pessoa. Para ENTRAR com biometria, mande {"login": e-mail ou CPF}: o
    desafio fica preso a essa pessoa (a resposta é igual exista ela ou não). Sem
    nada (cadastro), fica livre mas vale uma vez só."""
    if ip and not repo.consumir_orcamento(tipo="desafio", ip=ip,
                                         maximo=_MAX_DESAFIOS_IP_MIN, janela_min=1):
        raise HTTPException(status_code=429, detail="Muitos desafios pedidos. Aguarde um minuto.")
    dono = usuario
    if dono is None and login:
        dono = repo.obter_usuario_por_login(login)
    return biometria_service.criar_desafio(repo, usuario_id=dono["id"] if dono else None, modo=modo)
