"""Contexto assinado para o banco MySQL do Astro (equivalente ao aplicar_contexto do PG).

NÃO está ligado na aplicação: é o trecho que a API precisaria chamar para usar
o banco MySQL. Em backend/app/db/isolamento.py, no início de aplicar_contexto():

    if conn.dialect.name == 'mysql':
        from contexto_mysql import aplicar_contexto_mysql   # ou copiar a função
        return aplicar_contexto_mysql(conn, _contexto.get(), carteiras_operacao=carteiras_operacao)

O formato é o que astro_privado.ctx() confere (02_contexto_rls.sql):
  cid = CONNECTION_ID() desta conexão, tx = aleatório por transação, exp <= 35 s.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from sqlalchemy import text


def assinar(dados: dict, chave_b64: str) -> tuple[str, str]:
    """Serializa o contexto e devolve (corpo, prova HMAC-SHA256 em hex)."""
    chave = base64.urlsafe_b64decode(chave_b64)
    if len(chave) != 32:
        raise RuntimeError('DATABASE_CONTEXT_KEY precisa ter 32 bytes.')
    corpo = json.dumps(dados, sort_keys=True, separators=(',', ':'))
    return corpo, hmac.new(chave, corpo.encode(), hashlib.sha256).hexdigest()


def aplicar_contexto_mysql(conn, contexto: dict | None, *, chave_b64: str, carteiras_operacao=None) -> None:
    """Grava @astro_contexto/@astro_prova na sessão MySQL no início da transação.

    Sempre sobrescreve as duas variáveis: uma conexão reaproveitada do pool nunca
    carrega o contexto da requisição anterior (que, de qualquer forma, já teria
    outro "tx" e venceria em 35 s).
    """
    dados = dict(contexto or {'modo': 'sistema', 'usuario_id': None})
    dados['cid'] = conn.scalar(text('SELECT CONNECTION_ID()'))
    dados['tx'] = secrets.token_hex(16)
    dados['exp'] = int(time.time()) + 30
    if carteiras_operacao is not None:
        dados['carteiras_operacao'] = sorted(carteiras_operacao)
    corpo, prova = assinar(dados, chave_b64)
    conn.execute(text('SET @astro_contexto = :corpo, @astro_prova = :prova'), {'corpo': corpo, 'prova': prova})


def limpar_contexto_mysql(conn) -> None:
    """Chamar ao devolver a conexão ao pool (evento 'checkin' / 'reset')."""
    conn.execute(text('SET @astro_contexto = NULL, @astro_prova = NULL'))
