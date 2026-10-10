"""
TOTP (RFC 6238) para o 2º fator do admin da plataforma (SECURITY_AUDIT A-15).

O admin não tem rosto cadastrado (não é cliente): entra com senha + código de 6
dígitos do app autenticador (Google Authenticator, Microsoft Authenticator...).
HMAC-SHA1, passo de 30 s, aceita o passo anterior e o seguinte (relógio do
celular adiantado/atrasado). Implementado aqui para não puxar dependência nova.
"""

import base64
import hashlib
import hmac
import struct
import time

PASSO_SEG = 30
DIGITOS = 6
JANELA = 1  # passos aceitos antes/depois do atual


def segredo_valido(segredo: str | None) -> bool:
    """Base32 com pelo menos 160 bits (o tamanho que a RFC 4226 recomenda)."""
    try:
        return segredo is not None and len(_chave(segredo)) >= 20
    except ValueError:
        return False


def _chave(segredo: str) -> bytes:
    limpo = segredo.replace(" ", "").upper()
    return base64.b32decode(limpo + "=" * (-len(limpo) % 8))


def codigo(segredo: str, passo: int) -> str:
    mac = hmac.new(_chave(segredo), struct.pack(">Q", passo), hashlib.sha1).digest()
    deslocamento = mac[-1] & 0x0F
    numero = struct.unpack(">I", mac[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF
    return str(numero % 10**DIGITOS).zfill(DIGITOS)


def passo_do_codigo(segredo: str, informado: str, agora: float | None = None) -> int | None:
    """O passo em que o código vale (para marcar como usado), ou None."""
    informado = (informado or "").strip()
    if len(informado) != DIGITOS or not informado.isdigit():
        return None
    atual = int((time.time() if agora is None else agora) // PASSO_SEG)
    for passo in range(atual - JANELA, atual + JANELA + 1):
        if hmac.compare_digest(codigo(segredo, passo), informado):
            return passo
    return None
