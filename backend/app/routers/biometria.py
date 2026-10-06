from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.core import tempo
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
):
    """Gera o desafio de prova de vida (ação + validade). Logado, o desafio fica
    preso à pessoa; sem login (cadastro), fica livre mas vale uma vez só."""
    if ip and repo.contar_eventos(tipo="desafio", desde=tempo.agora() - timedelta(minutes=1), sucesso=None, ip=ip) >= _MAX_DESAFIOS_IP_MIN:
        raise HTTPException(status_code=429, detail="Muitos desafios pedidos. Aguarde um minuto.")
    repo.registrar_sessao_mfa(tipo="desafio", sucesso=True, usuario_id=usuario["id"] if usuario else None, ip=ip)
    return biometria_service.criar_desafio(repo, usuario_id=usuario["id"] if usuario else None)
