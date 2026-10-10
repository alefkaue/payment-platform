#!/bin/sh
# Entrypoint do backend de DEMONSTRAÇÃO (ver Dockerfile na raiz do repo).
# Os segredos vêm do ambiente (Render: render.yaml gera JWT_SECRET e ADMIN_SENHA e
# pede EMBEDDING_KEY; Azure: Key Vault). Nada é derivado do DATABASE_URL: quem
# descobrisse a URL do banco forjaria tokens (SEGURANCA.md, achado A6).
set -e

falta=""
for v in JWT_SECRET EMBEDDING_KEY ADMIN_SENHA CORS_ORIGINS; do
  eval "valor=\${$v:-}"
  [ -n "$valor" ] || falta="$falta $v"
done
if [ -n "$falta" ]; then
  echo "[entrypoint-demo] Faltam variáveis de ambiente:$falta" >&2
  echo "  JWT_SECRET:    python -c \"import secrets; print(secrets.token_urlsafe(48))\"" >&2
  echo "  EMBEDDING_KEY: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"" >&2
  echo "  ADMIN_SENHA:   senha forte (16+ caracteres)" >&2
  echo "  CORS_ORIGINS:  URL exata do app, ex.: https://astro-app.netlify.app" >&2
  exit 1
fi
if [ "${#JWT_SECRET}" -lt 32 ]; then
  echo "[entrypoint-demo] JWT_SECRET curto demais (mínimo 32 caracteres)." >&2
  exit 1
fi
python -c "import os; from cryptography.fernet import Fernet; Fernet(os.environ['EMBEDDING_KEY'].encode())" 2>/dev/null || {
  echo "[entrypoint-demo] EMBEDDING_KEY não é uma chave Fernet válida." >&2
  exit 1
}

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint-demo] Aplicando migrações Alembic..."
  alembic upgrade head
fi

echo "[entrypoint-demo] Iniciando API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-server-header
