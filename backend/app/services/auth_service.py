"""
Autenticação: login da PESSOA (e-mail + senha), JWT access + refresh com rotação
e detecção de reuso.

- O login é sempre da pessoa. Para operar uma empresa ela manda o header
  X-Conta com o número da conta PJ (ver deps.conta_atual) -- igual aos bancos
  digitais, em que você entra com seu CPF e escolhe a empresa.
- Rate limit duplo: falhas por e-mail (LOGIN_MAX_TENTATIVAS) e por IP
  (LOGIN_MAX_TENTATIVAS_IP). Só por e-mail, um ataque que testa a mesma senha em
  muitos e-mails a partir de um IP passava sem bloqueio.
- O aparelho do header X-Dispositivo-Id é registrado no login (não confiável se
  for novo; ver seguranca_service).
"""

import logging
import secrets
from datetime import timedelta
from functools import lru_cache

import jwt
from fastapi import HTTPException

from app.core import security, tempo
from app.core.config import get_settings
from app.repositories.repository import Repositorio

logger = logging.getLogger("payflow.auth")

@lru_cache
def _hash_falso() -> str:
    """Hash bcrypt válido de uma senha aleatória, para o login de e-mail
    inexistente gastar o mesmo tempo que um de verdade."""
    return security.hash_senha(secrets.token_urlsafe(16))


def _checar_rate_limit(repo: Repositorio, email: str, ip: str | None) -> None:
    s = get_settings()
    desde = tempo.agora() - timedelta(minutes=s.login_janela_min)
    if repo.contar_eventos(tipo="login", desde=desde, referencia=email) >= s.login_max_tentativas:
        raise HTTPException(status_code=429, detail="Muitas tentativas de login. Tente novamente em alguns minutos.")
    if ip and repo.contar_eventos(tipo="login", desde=desde, ip=ip) >= s.login_max_tentativas_ip:
        raise HTTPException(status_code=429, detail="Muitas tentativas de login a partir desta rede. Tente mais tarde.")


def autenticar(repo: Repositorio, *, email: str, senha: str, ip: str | None = None, dispositivo_hash: str | None = None) -> dict:
    email = email.lower().strip()
    _checar_rate_limit(repo, email, ip)
    usuario = repo.obter_usuario_por_login(email)
    ok = False
    if usuario and usuario["ativo"]:
        ok = security.verificar_senha(senha, usuario["senha_hash"])
    else:
        security.verificar_senha(senha, _hash_falso())  # tempo parecido: não revela se o e-mail existe

    if not ok:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=email, ip=ip,
                                  usuario_id=usuario["id"] if usuario else None)
        raise HTTPException(status_code=401, detail="E-mail/CPF ou senha inválidos.")

    repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=email, ip=ip)
    repo.registrar_log(ator=email, acao="login", ip=ip)
    if dispositivo_hash:
        repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=dispositivo_hash, nome=None)
    return usuario


def autenticar_biometria(repo: Repositorio, *, login: str, prova, ip: str | None = None,
                         dispositivo_hash: str | None = None) -> dict:
    """Entrar com o rosto (sem senha). O desafio precisa ter sido pedido com o
    mesmo login (POST /biometria/desafios {"login": ...}); o servidor confere a
    prova de vida e compara com o rosto cadastrado."""
    from app.services import seguranca_service

    ref = login.lower().strip()
    _checar_rate_limit(repo, ref, ip)
    usuario = repo.obter_usuario_por_login(ref)
    if not usuario or not usuario["ativo"] or not usuario["tem_biometria"]:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip)
        raise HTTPException(status_code=401, detail="Não foi possível entrar com biometria. Use a senha.")
    try:
        seguranca_service.verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="login_biometria")
    except HTTPException:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip, usuario_id=usuario["id"])
        raise
    repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
    repo.registrar_log(ator=usuario["email"], acao="login_biometria", ip=ip)
    if dispositivo_hash:
        repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=dispositivo_hash, nome=None)
    return usuario


def emitir_tokens(repo: Repositorio, usuario: dict) -> dict:
    access, access_exp = security.criar_access_token(usuario["id"], usuario["papel"])
    refresh_bruto, jti, refresh_exp = security.criar_refresh_token(usuario["id"])
    repo.salvar_refresh(usuario_id=usuario["id"], jti=jti, token_hash=security.hash_refresh(refresh_bruto), expira_em=refresh_exp)
    return {"access_token": access, "refresh_token": refresh_bruto, "token_type": "bearer", "access_expira_em": access_exp}


def renovar(repo: Repositorio, *, refresh_token: str, ip: str | None = None) -> dict:
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado.")
    registro = repo.obter_refresh(security.hash_refresh(refresh_token))
    if not registro:
        raise HTTPException(status_code=401, detail="Refresh token não reconhecido.")
    if registro["revogado"]:
        logger.warning("Reuso de refresh token detectado (usuario_id=%s). Revogando todas as sessões.", registro["usuario_id"])
        repo.revogar_todos_refresh(registro["usuario_id"])
        repo.registrar_log(ator=str(registro["usuario_id"]), acao="refresh_reuso_detectado", ip=ip)
        raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")
    usuario = repo.obter_usuario_por_id(registro["usuario_id"])
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa.")
    novos = emitir_tokens(repo, usuario)
    novo_payload = security.decodificar_token(novos["refresh_token"], "refresh")
    repo.revogar_refresh(payload["jti"], substituido_por=novo_payload["jti"])
    return novos


def logout(repo: Repositorio, *, refresh_token: str) -> None:
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        return
    repo.revogar_refresh(payload["jti"])
