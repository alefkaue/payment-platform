"""Contexto por requisição, assinado e preso à transação para políticas RLS."""
import base64
from contextvars import ContextVar
from contextlib import contextmanager
import hashlib
import hmac
import json
import time
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.segredos_webhook import validar_chaves

_contexto = ContextVar('astro_contexto_banco', default=None)
TABELAS_RLS = frozenset({'dispositivos','refresh_tokens','desafios_biometria',
                        'documentos_identidade','documentos_empresa','funcionarios','cartoes','limites',
                        'usuarios','vinculos','carteiras','transacoes','historico_saldo'})


class ContextoBanco:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        token = _contexto.set({'modo':'publico','usuario_id':None})
        try:
            return await self.app(scope, receive, send)
        finally:
            _contexto.reset(token)


def autorizar_usuario(usuario_id):
    atual = _contexto.get()
    if atual is not None and atual.get('modo') != 'sistema':
        if not isinstance(usuario_id,int) or isinstance(usuario_id,bool) or usuario_id < 1:
            raise ValueError('Titular inválido para o contexto de banco.')
        atual.update(modo='usuario',usuario_id=usuario_id)


def permitir_desafio(usuario_id):
    atual = _contexto.get()
    if atual is not None:
        atual['desafio_usuario_id'] = usuario_id


def permitir_caso(caso_id):
    atual = _contexto.get()
    if atual is not None:
        atual['kyc_caso_id'] = caso_id


@contextmanager
def contexto_teste(usuario_id=None, *, sistema=False):
    token = _contexto.set({'modo':'sistema' if sistema else 'usuario','usuario_id':usuario_id})
    try:
        yield
    finally:
        _contexto.reset(token)


def aplicar_contexto(conn, *, carteiras_operacao=None):
    if conn.dialect.name != 'postgresql':
        return
    habilitado = getattr(conn.engine, '_astro_rls', None)
    if habilitado is None:
        habilitado = bool(conn.scalar(text("SELECT to_regprocedure('public.astro_contexto()') IS NOT NULL")))
        conn.engine._astro_rls = habilitado
    if not habilitado:
        return
    s = get_settings()
    chaves = validar_chaves(s.database_context_key, proibidas=[s.jwt_secret,s.embedding_key,
        *(s.pii_keys or '').split(','),s.pii_index_key,*(s.webhook_keys or '').split(',')])
    if len(chaves) != 1:
        raise RuntimeError('DATABASE_CONTEXT_KEY exige uma chave exclusiva.')
    pid, tx = conn.execute(text('SELECT pg_backend_pid(), txid_current()')).one()
    dados = {**(_contexto.get() or {'modo':'sistema','usuario_id':None}),
             'pid':pid,'tx':tx,'exp':int(time.time())+30}
    if carteiras_operacao is not None:
        dados['carteiras_operacao'] = sorted(carteiras_operacao)
    corpo = json.dumps(dados,sort_keys=True,separators=(',',':'))
    assinatura = hmac.new(base64.urlsafe_b64decode(chaves[0]),corpo.encode(),hashlib.sha256).hexdigest()
    conn.execute(text("SELECT set_config('astro.contexto',:corpo,true),set_config('astro.prova',:prova,true)"),
                 {'corpo':corpo,'prova':assinatura})


@event.listens_for(Session,'after_begin')
def _contexto_da_transacao(session, transaction, connection):
    aplicar_contexto(connection, carteiras_operacao=session.info.get("carteiras_operacao"))
