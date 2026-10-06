"""
Autenticação: login com e-mail+senha, emissão de JWT (access + refresh) e rotação
de refresh token. Fecha o item #1 da auditoria (nenhum endpoint exigia login).

Fluxo de refresh (rotação + detecção de reuso):
- No login emitimos access (curto) + refresh (longo). Guardamos só o HASH do
  refresh no banco.
- Em /auth/refresh, o refresh apresentado é validado (assinatura, expiração, não
  revogado) e ROTACIONADO: o antigo é revogado e um novo par é emitido.
- Se um refresh JÁ revogado reaparece (reuso -- sinal de token roubado/clonado),
  revogamos TODOS os refresh daquele usuário (derruba todas as sessões) e negamos.

Rate-limit: tentativas de login falhas por e-mail dentro da janela (gravadas em
sessoes_mfa tipo="login") -- acima do limite, 429. Fecha parte do item #3.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from app.core import security
from app.core.config import get_settings
from app.repositories.repository import Repositorio

logger = logging.getLogger("payflow.auth")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _checar_rate_limit_login(repo: Repositorio, email: str) -> None:
    s = get_settings()
    desde = _agora() - timedelta(minutes=s.login_janela_min)
    falhas = repo.contar_falhas_recentes(tipo="login", desde=desde, referencia=email.lower().strip())
    if falhas >= s.login_max_tentativas:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Tente novamente em alguns minutos.",
        )


def autenticar(repo: Repositorio, *, email: str, senha: str, ip: str | None = None) -> dict:
    _checar_rate_limit_login(repo, email)
    usuario = repo.obter_usuario_por_email(email)

    # Mensagem genérica idêntica para e-mail inexistente OU senha errada -- não
    # revela se o e-mail existe. Verifica a senha mesmo com usuário None usando um
    # hash dummy, pra o tempo de resposta não denunciar a existência da conta.
    ok = False
    if usuario and usuario["ativo"]:
        ok = security.verificar_senha(senha, usuario["senha_hash"])
    else:
        security.verificar_senha(senha, "$2b$12$" + "x" * 53)  # gasta tempo similar

    if not ok:
        repo.registrar_sessao_mfa(
            tipo="login", sucesso=False, referencia=email.lower().strip(), ip=ip,
            usuario_id=usuario["id"] if usuario else None,
        )
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")

    repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=email.lower().strip(), ip=ip)
    repo.registrar_log(ator=email.lower().strip(), acao="login", ip=ip)
    return usuario


def emitir_tokens(repo: Repositorio, usuario: dict) -> dict:
    access, access_exp = security.criar_access_token(usuario["id"], usuario["papel"])
    refresh_bruto, jti, refresh_exp = security.criar_refresh_token(usuario["id"])
    repo.salvar_refresh(
        usuario_id=usuario["id"],
        jti=jti,
        token_hash=security.hash_refresh(refresh_bruto),
        expira_em=refresh_exp,
    )
    return {
        "access_token": access,
        "refresh_token": refresh_bruto,
        "token_type": "bearer",
        "access_expira_em": access_exp,
    }


def renovar(repo: Repositorio, *, refresh_token: str, ip: str | None = None) -> dict:
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado.")

    registro = repo.obter_refresh(security.hash_refresh(refresh_token))
    if not registro:
        raise HTTPException(status_code=401, detail="Refresh token não reconhecido.")

    if registro["revogado"]:
        # Reuso de um refresh já rotacionado -> possível roubo. Derruba tudo.
        logger.warning("Reuso de refresh token detectado (usuario_id=%s). Revogando todas as sessões.", registro["usuario_id"])
        repo.revogar_todos_refresh(registro["usuario_id"])
        repo.registrar_log(ator=str(registro["usuario_id"]), acao="refresh_reuso_detectado", ip=ip)
        raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")

    usuario = repo.obter_usuario_por_id(registro["usuario_id"])
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa.")

    # Rotação: revoga o atual e emite um novo par.
    novos = emitir_tokens(repo, usuario)
    novo_payload = security.decodificar_token(novos["refresh_token"], "refresh")
    repo.revogar_refresh(payload["jti"], substituido_por=novo_payload["jti"])
    return novos


def logout(repo: Repositorio, *, refresh_token: str) -> None:
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        return  # logout é idempotente -- token já inválido, nada a fazer
    repo.revogar_refresh(payload["jti"])
