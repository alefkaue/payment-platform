#!/bin/sh
# Gera o .env.docker com segredos de TESTE para o stack local (docker-compose.hub.yml).
# Segredos de teste -- NÃO use em produção. O .env.docker é ignorado pelo git.
set -eu
cd "$(dirname "$0")"

if [ -f .env.docker ]; then
  printf '.env.docker já existe. Sobrescrever? (s/N) '
  read -r r; [ "$r" = "s" ] || [ "$r" = "S" ] || { echo "cancelado."; exit 0; }
fi

fernet() { openssl rand -base64 32 | tr '+/' '-_'; }   # chave Fernet (urlsafe, 32 bytes)

cat > .env.docker <<EOF
# SEGREDOS DE TESTE do stack local (docker-compose.hub.yml). NÃO use em produção.
POSTGRES_USER=payflow
POSTGRES_DB=payflow
POSTGRES_PASSWORD=$(openssl rand -hex 16)
DATABASE_APP_PASSWORD=$(openssl rand -hex 16)
DATABASE_MIGRATION_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_SENHA=$(openssl rand -base64 18)
EMBEDDING_KEY=$(fernet)
WEBHOOK_KEYS=$(fernet)
PII_KEYS=$(fernet)
PII_INDEX_KEY=$(fernet)
DATABASE_CONTEXT_KEY=$(fernet)
EOF

chmod 600 .env.docker
echo ".env.docker gerado. Agora: docker compose -f docker-compose.hub.yml --env-file .env.docker up -d"
