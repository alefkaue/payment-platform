#!/bin/sh
# Entrypoint do container de backend.
# Com Postgres (DATABASE_URL definida), aplica as migrações versionadas (Alembic)
# antes de subir a API -- em produção o schema é gerido pelo Alembic, não pelo
# create_all. Sem DATABASE_URL (dev/SQLite), o create_all do boot cuida do schema.
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint] Aplicando migrações Alembic..."
  alembic upgrade head
fi

echo "[entrypoint] Iniciando API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
