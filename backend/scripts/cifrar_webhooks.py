"""Migra/rotaciona segredos sem imprimir dados. Executar com papel migrador e API parada."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from app.core.segredos_webhook import cifrar, decifrar, validar_chaves
from app.core.config import get_settings


def migrar(connection) -> int:
    s = get_settings()
    validar_chaves(s.webhook_keys, proibidas=[s.embedding_key, s.jwt_secret])
    stmt = 'SELECT id, empresa_id, segredo FROM public.webhooks ORDER BY id FOR UPDATE'
    if connection.dialect.name == 'sqlite':
        stmt = 'SELECT id, empresa_id, segredo FROM webhooks ORDER BY id'
    quantidade = 0
    for row in connection.execute(text(stmt)).mappings().all():
        segredo = decifrar(row['segredo'], row['empresa_id'], permitir_legado=True)
        connection.execute(text('UPDATE webhooks SET segredo = :valor WHERE id = :id'),
                           {'valor': cifrar(segredo, row['empresa_id']), 'id': row['id']})
        quantidade += 1
    return quantidade


if __name__ == '__main__':
    url = os.environ.get('DATABASE_MIGRATION_URL')
    if not url:
        raise SystemExit('Defina DATABASE_MIGRATION_URL e WEBHOOK_KEYS no ambiente protegido.')
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            total = migrar(connection)
        print(json.dumps({'webhooks_cifrados_ou_rotacionados': total}))
    except Exception:
        # Não imprimir exceções SQL, connection string, plaintext ou ciphertext.
        raise SystemExit('Criptografia não concluída; transação revertida. Confira chaves e migração de esquema.') from None
    finally:
        engine.dispose()
