"""
Primitivas de segurança, isoladas aqui para o resto do código nunca mexer em
cripto na mão:

- Hash de senha: **Argon2id** (argon2-cffi) com os parâmetros mínimos do OWASP
  Password Storage Cheat Sheet (m=19 MiB, t=2, p=1). Hashes bcrypt antigos
  continuam sendo aceitos e são trocados por Argon2id no próximo login
  (`precisa_rehash`) -- migração sem forçar ninguém a trocar a senha.
- JWT (PyJWT, HS256) seguindo o RFC 8725: algoritmo fixo na validação, `iss` e
  `aud` conferidos, tipo explícito no cabeçalho (`typ`) E no payload (`type`), e
  tipos mutuamente exclusivos -- um token de MFA ou refresh nunca vale como access.
- Amarração ao aparelho: o access token carrega `dev` (SHA-256 do
  X-Dispositivo-Id do login) e `sid` (sessão). Token vazado não funciona em outro
  aparelho e "encerrar sessão" derruba o access na hora (ver deps.usuario_atual).
- Hash de refresh token (SHA-256): no banco fica só o hash.
- Template biométrico cifrado (Fernet) com o nome do modelo junto -- vetores de
  motores diferentes (Facenet x SFace) nunca são comparados entre si.

Em desenvolvimento, se JWT_SECRET / EMBEDDING_KEY não vierem no ambiente, geramos
um valor efêmero e avisamos no log. Em produção isso é erro duro.
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger("payflow.security")

# OWASP Password Storage Cheat Sheet: Argon2id, m=19 MiB, t=2, p=1 (mínimo).
_ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_SENHA_MAX_BYTES = 1024  # evita DoS com senha gigante (Argon2 não trunca)

# Tipos de token -> valor do cabeçalho `typ` (RFC 8725 §3.11, explicit typing).
_TYP = {"access": "at+jwt", "refresh": "rt+jwt", "mfa": "mfa+jwt"}


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
    segredo = _exigir_segredo("JWT_SECRET", get_settings().jwt_secret, lambda: secrets.token_urlsafe(48))
    if get_settings().em_producao and len(segredo) < 32:
        raise RuntimeError("JWT_SECRET curto demais para produção (mínimo 32 caracteres).")
    return segredo


def _fernet() -> Fernet:
    chave = _exigir_segredo("EMBEDDING_KEY", get_settings().embedding_key, lambda: Fernet.generate_key().decode())
    return Fernet(chave.encode() if isinstance(chave, str) else chave)


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------
def hash_senha(senha: str) -> str:
    if len(senha.encode("utf-8")) > _SENHA_MAX_BYTES:
        raise ValueError("Senha muito longa.")
    return _ph.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    if len(senha.encode("utf-8")) > _SENHA_MAX_BYTES or not senha_hash:
        return False
    if senha_hash.startswith("$argon2"):
        try:
            return _ph.verify(senha_hash, senha)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if senha_hash.startswith("$2"):  # bcrypt legado (v6/v7): só verifica, nunca gera
        try:
            return bcrypt.checkpw(senha.encode("utf-8")[:72], senha_hash.encode("utf-8"))
        except ValueError:
            return False
    return False


def precisa_rehash(senha_hash: str) -> bool:
    """True para bcrypt legado ou Argon2 com parâmetros antigos."""
    if not senha_hash.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(senha_hash)
    except InvalidHashError:
        return True


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _criar_token(sub: str, tipo: str, expira_em: timedelta, extra: dict | None = None) -> tuple[str, str, datetime]:
    """Retorna (token, jti, expira_em_utc)."""
    s = get_settings()
    agora = datetime.now(timezone.utc)
    exp = agora + expira_em
    jti = secrets.token_urlsafe(16)
    payload = {
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "sub": str(sub),
        "type": tipo,
        "jti": jti,
        "iat": int(agora.timestamp()),
        "nbf": int(agora.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None})
    token = jwt.encode(payload, _jwt_secret(), algorithm=s.jwt_algoritmo, headers={"typ": _TYP[tipo]})
    return token, jti, exp


def _cnf(jkt: str | None) -> dict | None:
    """Confirmação da chave (RFC 9449): o token só vale com prova DPoP desta chave."""
    return {"jkt": jkt} if jkt else None


def criar_access_token(usuario_id: int, papel: str, *, dispositivo_hash: str | None = None,
                       sessao_id: str | None = None, jkt: str | None = None) -> tuple[str, datetime]:
    s = get_settings()
    token, _, exp = _criar_token(
        usuario_id, "access", timedelta(minutes=s.access_token_exp_min),
        extra={"papel": papel, "dev": dispositivo_hash, "sid": sessao_id, "cnf": _cnf(jkt)},
    )
    return token, exp


def criar_refresh_token(usuario_id: int, *, sessao_id: str | None = None,
                        jkt: str | None = None) -> tuple[str, str, datetime]:
    """Retorna (token_bruto, jti, expira_em). No banco vai só hash_refresh(token)."""
    s = get_settings()
    return _criar_token(usuario_id, "refresh", timedelta(days=s.refresh_token_exp_dias),
                        extra={"sid": sessao_id, "cnf": _cnf(jkt)})


def criar_mfa_token(usuario_id: int, *, dispositivo_hash: str | None,
                    jkt: str | None = None) -> tuple[str, str, datetime]:
    """Token intermediário: a senha confere, falta a prova facial. Só serve em
    POST /auth/login/mfa e expira em minutos."""
    s = get_settings()
    return _criar_token(usuario_id, "mfa", timedelta(minutes=s.mfa_token_exp_min),
                        extra={"dev": dispositivo_hash, "cnf": _cnf(jkt)})


def decodificar_token(token: str, tipo_esperado: str) -> dict:
    """Valida assinatura, algoritmo, exp/nbf, iss, aud e o tipo (cabeçalho e
    payload). Levanta jwt.PyJWTError ou ValueError -- quem chama traduz pra 401."""
    s = get_settings()
    cabecalho = jwt.get_unverified_header(token)
    if cabecalho.get("typ") != _TYP[tipo_esperado]:
        raise ValueError(f"Token do tipo errado (esperado {tipo_esperado}).")
    payload = jwt.decode(
        token, _jwt_secret(), algorithms=[s.jwt_algoritmo], issuer=s.jwt_issuer, audience=s.jwt_audience,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
    )
    if payload.get("type") != tipo_esperado:
        raise ValueError(f"Token do tipo '{payload.get('type')}', esperado '{tipo_esperado}'.")
    return payload


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def novo_sessao_id() -> str:
    return secrets.token_urlsafe(18)


# ---------------------------------------------------------------------------
# Template biométrico cifrado em repouso (LGPD: dado sensível)
# ---------------------------------------------------------------------------
def cifrar_embedding(vetor: list[float], modelo: str = "sface") -> bytes:
    bruto = json.dumps({"m": modelo, "v": [float(x) for x in vetor]}).encode("utf-8")
    return _fernet().encrypt(bruto)


def decifrar_embedding(blob: bytes) -> dict | None:
    """{"modelo": str, "vetor": list[float]} ou None (chave trocada/corrompido).
    Templates da v7 eram uma lista pura do Facenet -- marcados como "facenet"."""
    try:
        bruto = _fernet().decrypt(blob)
    except InvalidToken:
        logger.error("Falha ao decifrar template facial -- EMBEDDING_KEY mudou?")
        return None
    dado = json.loads(bruto.decode("utf-8"))
    if isinstance(dado, list):
        return {"modelo": "facenet", "vetor": dado}
    return {"modelo": dado.get("m", "desconhecido"), "vetor": dado.get("v", [])}
