"""Cifragem autenticada e índice HMAC; chaves ficam fora do banco e do Git."""
import base64
import hashlib
import hmac
import json
from datetime import date
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from app.core.config import get_settings
from app.core.segredos_webhook import validar_chaves

PREFIXO = 'pii:v1:'


def validar_configuracao(s):
    proibidas = [s.jwt_secret, s.embedding_key, *(s.webhook_keys or '').split(','), s.database_context_key]
    try:
        chaves = validar_chaves(s.pii_keys, proibidas=proibidas)
        indice = validar_chaves(s.pii_index_key, proibidas=[*proibidas, *chaves])
        if len(indice) != 1:
            raise ValueError()
    except (RuntimeError, ValueError):
        raise RuntimeError('PII_KEYS e PII_INDEX_KEY devem ser chaves distintas, persistentes e separadas dos outros segredos.') from None
    return chaves, base64.urlsafe_b64decode(indice[0])


def indice(valor, dominio):
    if valor is None:
        return None
    _, chave = validar_configuracao(get_settings())
    serial = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hmac.new(chave, (dominio + '\0' + serial).encode(), hashlib.sha256).hexdigest()


def cifrar(valor, campo, dominio=None, formato='texto'):
    if valor is None:
        return None
    if formato == 'data':
        valor = valor.isoformat() if isinstance(valor, date) else str(valor)
    chaves, _ = validar_configuracao(get_settings())
    resumo = indice(valor, dominio) if dominio else '0' * 64
    corpo = json.dumps({'campo': campo, 'indice': resumo, 'valor': valor}, ensure_ascii=False,
                      separators=(',', ':')).encode()
    token = MultiFernet([Fernet(k) for k in chaves]).encrypt(corpo).decode()
    return PREFIXO + resumo + ':' + token


def decifrar(valor, campo, dominio=None, formato='texto', *, permitir_legado=False):
    if valor is None:
        return None
    if not isinstance(valor, str) or not valor.startswith(PREFIXO):
        if not permitir_legado:
            raise RuntimeError('Dados pessoais legados: execute a migração de cifragem.')
        if formato == 'json' and isinstance(valor, str):
            return json.loads(valor)
        if formato == 'data' and isinstance(valor, str):
            return date.fromisoformat(valor)
        return valor
    chaves, _ = validar_configuracao(get_settings())
    try:
        resumo, token = valor[len(PREFIXO):].split(':', 1)
        dados = json.loads(MultiFernet([Fernet(k) for k in chaves]).decrypt(token.encode()))
        esperado = indice(dados['valor'], dominio) if dominio else '0' * 64
        if dados['campo'] != campo or not hmac.compare_digest(resumo, esperado) or dados['indice'] != resumo:
            raise InvalidToken()
        return date.fromisoformat(dados['valor']) if formato == 'data' else dados['valor']
    except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
        raise RuntimeError('Não foi possível autenticar o campo pessoal cifrado.') from None
