"""
Prova de posse da chave (DPoP, RFC 9449) -- SEGURANCA.md item 2.

Problema que resolve: antes, o token era "preso ao aparelho" só pelo header
X-Dispositivo-Id, um valor que o próprio cliente escolhe e guarda no
localStorage. Quem roubava o token (XSS, extensão, malware) roubava o id junto e
usava de outra máquina.

Agora o app gera um par de chaves ECDSA P-256 **não exportável** (WebCrypto no
navegador; Keystore/Keychain no app nativo) e manda, em CADA requisição, um JWT
curto no header `DPoP`, assinado com a chave privada e com a pública no
cabeçalho (`jwk`). O servidor:

1. confere a assinatura com a `jwk` do próprio cabeçalho (só aceita ES256 e
   recusa chave privada no cabeçalho);
2. confere `htm` (método), `htu` (caminho, sem query), `iat` (±60 s) e `jti`
   (uso único: uma prova capturada não pode ser reenviada);
3. calcula a impressão da chave (thumbprint RFC 7638, `jkt`).

No login, o `jkt` vai para dentro do mfa_token, do access e do refresh
(`cnf.jkt`). Daí em diante, cada requisição precisa de uma prova feita com A
MESMA chave e com `ath` = hash do access token usado. Token roubado sem a chave
privada não serve; e a chave não sai do aparelho.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import timedelta
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException
from jwt.algorithms import ECAlgorithm

from app.core import tempo
from app.core.config import get_settings

ALGORITMOS = ("ES256",)
TYP = "dpop+jwt"
_CAMPOS_PUBLICOS_EC = ("crv", "kty", "x", "y")


def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def thumbprint(jwk: dict) -> str:
    """Impressão da chave pública (RFC 7638): SHA-256 do JSON canônico."""
    canonico = json.dumps({k: jwk[k] for k in _CAMPOS_PUBLICOS_EC}, separators=(",", ":"), sort_keys=True)
    return _b64url(hashlib.sha256(canonico.encode("utf-8")).digest())


def hash_access_token(token: str) -> str:
    """`ath` da prova: base64url(SHA-256(access token))."""
    return _b64url(hashlib.sha256(token.encode("ascii")).digest())


def _recusar(motivo: str) -> HTTPException:
    return HTTPException(status_code=401, detail=f"Prova de posse (DPoP) inválida: {motivo}",
                         headers={"WWW-Authenticate": 'DPoP algs="ES256"'})


def verificar(prova: str | None, *, metodo: str, caminho: str, repo, access_token: str | None = None) -> str:
    """Valida a prova e devolve o `jkt` da chave. Levanta 401 se algo não bater."""
    if not prova:
        raise _recusar("envie o header DPoP assinado pela chave deste aparelho.")
    if len(prova) > 4096:
        raise _recusar("prova grande demais.")
    try:
        cabecalho = jwt.get_unverified_header(prova)
    except jwt.PyJWTError:
        raise _recusar("formato.")
    if cabecalho.get("typ") != TYP or cabecalho.get("alg") not in ALGORITMOS:
        raise _recusar("tipo ou algoritmo não aceito.")
    jwk = cabecalho.get("jwk")
    if (not isinstance(jwk, dict) or jwk.get("kty") != "EC" or jwk.get("crv") != "P-256"
            or "d" in jwk or not all(isinstance(jwk.get(k), str) for k in _CAMPOS_PUBLICOS_EC)):
        raise _recusar("chave pública ausente ou inválida.")
    try:
        chave = ECAlgorithm.from_jwk(json.dumps(jwk))
        corpo = jwt.decode(prova, chave, algorithms=list(ALGORITMOS),
                           options={"require": ["jti", "htm", "htu", "iat"], "verify_aud": False})
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _recusar("assinatura.")

    s = get_settings()
    if str(corpo["htm"]).upper() != metodo.upper():
        raise _recusar("método diferente do assinado.")
    if urlsplit(str(corpo["htu"])).path.rstrip("/") != caminho.rstrip("/"):
        raise _recusar("endereço diferente do assinado.")
    agora = tempo.agora().timestamp()
    if not isinstance(corpo["iat"], (int, float)) or abs(agora - corpo["iat"]) > s.dpop_janela_seg:
        raise _recusar("horário fora da janela (confira o relógio do aparelho).")
    if access_token is not None and corpo.get("ath") != hash_access_token(access_token):
        raise _recusar("não corresponde ao token de acesso.")
    jti = str(corpo["jti"])
    if not 8 <= len(jti) <= 64:
        raise _recusar("identificador (jti) inválido.")
    # Uso único: guardamos o jti pelo dobro da janela (cobre relógio adiantado/atrasado).
    if not repo.registrar_jti_dpop(jti, expira_em=tempo.agora() + timedelta(seconds=2 * s.dpop_janela_seg)):
        raise _recusar("prova reutilizada.")
    return thumbprint(jwk)


def jkt_do_token(payload: dict) -> str | None:
    cnf = payload.get("cnf")
    return cnf.get("jkt") if isinstance(cnf, dict) else None
