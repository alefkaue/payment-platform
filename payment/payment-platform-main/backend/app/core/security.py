"""
Primitivas de segurança, isoladas aqui para o resto do código nunca mexer em
cripto na mão:

- Hash de senha (bcrypt via passlib) -- nunca guardamos senha em texto puro.
- JWT access + refresh (PyJWT) -- assinados com JWT_SECRET, cada um com um `type`
  embutido pra um access token nunca ser aceito onde se espera um refresh.
- Hash de refresh token (SHA-256) -- no banco guardamos só o hash do refresh, não
  o token em si; se o banco vazar, os refresh tokens não são reutilizáveis.
- Cifra do embedding facial (Fernet) -- o vetor do rosto é dado biométrico (LGPD,
  dado sensível), então vai cifrado em repouso. Fecha o item #12 da auditoria.

Em desenvolvimento, se JWT_SECRET / EMBEDDING_KEY não vierem no ambiente, geramos
um valor efêmero e avisamos no log (ver core/config.py). Em produção isso é um erro
duro (ver `_exigir_segredo`).
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import get_settings

logger = logging.getLogger("payflow.security")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt trunca em 72 bytes silenciosamente -- validamos o tamanho antes de hashear
# pra ninguém achar que uma senha de 100 chars está sendo usada inteira.
_BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------------------
# Segredos (gerados de forma efêmera em dev; obrigatórios em produção)
# ---------------------------------------------------------------------------
_segredos_efemeros: dict[str, str] = {}


def _exigir_segredo(nome_env: str, valor: str | None, gerar) -> str:
    settings = get_settings()
    if valor:
        return valor
    if settings.em_producao:
        raise RuntimeError(
            f"{nome_env} é obrigatório em produção -- configure via variável de "
            f"ambiente / Azure Key Vault. Nunca use segredo efêmero em produção."
        )
    if nome_env not in _segredos_efemeros:
        _segredos_efemeros[nome_env] = gerar()
        logger.warning(
            "%s não definido -- usando segredo EFÊMERO de desenvolvimento "
            "(tokens/dados cifrados não sobrevivem a reboot). NÃO use em produção.",
            nome_env,
        )
    return _segredos_efemeros[nome_env]


def _jwt_secret() -> str:
    return _exigir_segredo("JWT_SECRET", get_settings().jwt_secret, lambda: secrets.token_urlsafe(48))


def _fernet() -> Fernet:
    chave = _exigir_segredo("EMBEDDING_KEY", get_settings().embedding_key, lambda: Fernet.generate_key().decode())
    return Fernet(chave.encode() if isinstance(chave, str) else chave)


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------
def hash_senha(senha: str) -> str:
    if len(senha.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError("Senha muito longa (máximo 72 bytes).")
    return _pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return _pwd_context.verify(senha, senha_hash)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT access + refresh
# ---------------------------------------------------------------------------
def _criar_token(sub: str, tipo: str, expira_em: timedelta, extra: dict | None = None) -> tuple[str, str, datetime]:
    """Retorna (token, jti, expira_em_utc). `jti` é o id único do token -- usado
    pra rastrear/revogar refresh tokens individualmente."""
    agora = datetime.now(timezone.utc)
    exp = agora + expira_em
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": str(sub),
        "type": tipo,
        "jti": jti,
        "iat": int(agora.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, _jwt_secret(), algorithm=get_settings().jwt_algoritmo)
    return token, jti, exp


def criar_access_token(usuario_id: int, papel: str) -> tuple[str, datetime]:
    settings = get_settings()
    token, _, exp = _criar_token(
        usuario_id, "access", timedelta(minutes=settings.access_token_exp_min), extra={"papel": papel}
    )
    return token, exp


def criar_refresh_token(usuario_id: int) -> tuple[str, str, datetime]:
    """Retorna (token_bruto, jti, expira_em). O token_bruto vai pro cliente; no
    banco guardamos só hash_refresh(token_bruto)."""
    settings = get_settings()
    return _criar_token(usuario_id, "refresh", timedelta(days=settings.refresh_token_exp_dias))


def decodificar_token(token: str, tipo_esperado: str) -> dict:
    """Valida assinatura + expiração e confere o `type`. Levanta jwt.PyJWTError
    (ou ValueError se o type não bater) -- quem chama traduz pra 401."""
    payload = jwt.decode(token, _jwt_secret(), algorithms=[get_settings().jwt_algoritmo])
    if payload.get("type") != tipo_esperado:
        raise ValueError(f"Token do tipo '{payload.get('type')}', esperado '{tipo_esperado}'.")
    return payload


def hash_refresh(token: str) -> str:
    """Hash determinístico (SHA-256) do refresh token, pra guardar/comparar no
    banco sem armazenar o token em si."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Embedding facial cifrado em repouso (LGPD)
# ---------------------------------------------------------------------------
def cifrar_embedding(embedding: list[float]) -> bytes:
    bruto = json.dumps(embedding).encode("utf-8")
    return _fernet().encrypt(bruto)


def decifrar_embedding(blob: bytes) -> list[float] | None:
    try:
        bruto = _fernet().decrypt(blob)
    except InvalidToken:
        # Chave trocada (ex: segredo efêmero após reboot) -- não dá pra ler o
        # template antigo. Trata como "sem biometria" em vez de derrubar a request.
        logger.error("Falha ao decifrar embedding facial -- chave EMBEDDING_KEY mudou?")
        return None
    return json.loads(bruto.decode("utf-8"))
