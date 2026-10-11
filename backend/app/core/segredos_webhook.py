"""Criptografia autenticada de segredo HMAC, com separação e rotação de chaves."""
import base64
import binascii
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from app.core.config import get_settings

PREFIXO = "enc:v1:"


def validar_chaves(valor: str | None, proibidas=()) -> list[str]:
    chaves = [p.strip() for p in (valor or "").split(",") if p.strip()]
    try:
        if not chaves or len(chaves) > 5 or len(set(chaves)) != len(chaves):
            raise ValueError()
        materiais = []
        for chave in chaves:
            material = base64.b64decode(chave.encode(), altchars=b"-_", validate=True)
            if len(material) != 32 or base64.urlsafe_b64encode(material).decode() != chave:
                raise ValueError()
            Fernet(chave.encode())
            materiais.append(material)
            if chave in proibidas:
                raise ValueError()
            for proibida in proibidas:
                if proibida:
                    try:
                        igual = base64.urlsafe_b64decode(proibida.encode()) == material
                    except (ValueError, binascii.Error):
                        igual = False
                    if igual:
                        raise ValueError()
        if len(set(materiais)) != len(materiais):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise RuntimeError("WEBHOOK_KEYS exige de 1 a 5 chaves Fernet distintas e separadas de JWT/biometria.") from None
    return chaves


def _cofre() -> MultiFernet:
    s = get_settings()
    return MultiFernet([Fernet(k.encode()) for k in validar_chaves(
        s.webhook_keys, proibidas=[s.embedding_key, s.jwt_secret])])


def cifrar(segredo: str, empresa_id: int) -> str:
    dado = f"astro-webhook-v1:{empresa_id}:".encode() + segredo.encode()
    return PREFIXO + _cofre().encrypt(dado).decode()


def decifrar(valor: str, empresa_id: int, *, permitir_legado: bool = False) -> str:
    if not valor.startswith(PREFIXO):
        if permitir_legado:
            return valor
        raise RuntimeError("Segredo de webhook legado: execute a migração de criptografia.")
    try:
        dado = _cofre().decrypt(valor[len(PREFIXO):].encode())
        contexto = f"astro-webhook-v1:{empresa_id}:".encode()
        if not dado.startswith(contexto):
            raise InvalidToken()
        return dado[len(contexto):].decode()
    except (InvalidToken, UnicodeError):
        raise RuntimeError("Não foi possível autenticar o segredo de webhook.") from None
