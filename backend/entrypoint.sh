#!/bin/sh
# Entrypoint do container de backend.
# Com Postgres (DATABASE_URL definida), aplica as migrações versionadas (Alembic)
# antes de subir a API -- em produção o schema é gerido pelo Alembic, não pelo
# create_all. Sem DATABASE_URL (dev/SQLite), o create_all do boot cuida do schema.
set -e

# A API não recebe credenciais de DDL. Migrações rodam em job separado.
# RUN_MIGRATIONS=1 é somente compatibilidade para desenvolvimento.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  if [ "${AMBIENTE:-desenvolvimento}" = "producao" ] || [ "${AMBIENTE:-}" = "production" ] || [ "${AMBIENTE:-}" = "prod" ]; then
    echo "Migrações de produção devem rodar em job separado." >&2
    exit 1
  fi
  alembic upgrade head
fi

# --no-server-header: não anuncia "uvicorn" nas respostas.
# O IP do cliente NÃO vem do --proxy-headers do uvicorn: quem decide é
# app/deps.py:ip_cliente (PROXIES_CONFIAVEIS / FRONT_DOOR_ID).
echo "[entrypoint] Iniciando API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --no-server-header --no-proxy-headers
