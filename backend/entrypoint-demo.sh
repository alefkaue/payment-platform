#!/bin/sh
# Entrypoint do backend de DEMONSTRAÇÃO (ver Dockerfile na raiz do repo).
# Os segredos que não vierem no ambiente são derivados do DATABASE_URL: ficam
# estáveis entre reinícios (o plano grátis dorme e acorda) sem ir para o git.
set -e

derivar() {
  python -c "import base64,hashlib,os,sys; d=hashlib.sha256((sys.argv[1]+os.environ.get('DATABASE_URL','astro-demo')).encode()).digest(); print(base64.urlsafe_b64encode(d).decode() if sys.argv[2]=='fernet' else d.hex())" "$1" "$2"
}
[ -n "$JWT_SECRET" ] || export JWT_SECRET="$(derivar jwt hex)"
[ -n "$EMBEDDING_KEY" ] || export EMBEDDING_KEY="$(derivar embedding fernet)"
[ -n "$ADMIN_SENHA" ] || export ADMIN_SENHA="$(derivar admin hex)"

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint-demo] Aplicando migrações Alembic..."
  alembic upgrade head
fi

echo "[entrypoint-demo] Iniciando API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
