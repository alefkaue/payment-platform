"""Provisiona somente a chave de prova de contexto com o papel migrador."""
import base64
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from app.core.config import get_settings
from app.core.segredos_webhook import validar_chaves


def configurar(conn):
    s=get_settings()
    chaves=validar_chaves(s.database_context_key,proibidas=[s.jwt_secret,s.embedding_key,
        *(s.webhook_keys or '').split(','),*(s.pii_keys or '').split(','),s.pii_index_key])
    if len(chaves)!=1: raise RuntimeError('DATABASE_CONTEXT_KEY exige uma chave exclusiva.')
    conn.execute(text('INSERT INTO astro_privado.contexto_chave(id,chave) VALUES(1,:chave) ON CONFLICT(id) DO UPDATE SET chave=EXCLUDED.chave'),
                 {'chave':base64.urlsafe_b64decode(chaves[0])})


if __name__=='__main__':
    url=os.environ.get('DATABASE_MIGRATION_URL')
    if not url: raise SystemExit('Defina DATABASE_MIGRATION_URL no ambiente protegido.')
    engine=create_engine(url,hide_parameters=True)
    try:
        with engine.begin() as conn: configurar(conn)
        print('Chave de contexto configurada; nenhum segredo exibido.')
    except Exception:
        raise SystemExit('Isolamento não configurado; confira migrações, privilégios e chave.') from None
    finally: engine.dispose()
