#!/usr/bin/env bash
# Prepara os segredos do perfil local; --hub baixa imagens de apresentação.
# Uso: ./install.sh [--local|--hub]
set -euo pipefail
umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PERFIL="${1:---local}"
if [ "$#" -gt 1 ] || { [ "$PERFIL" != "--local" ] && [ "$PERFIL" != "--hub" ]; }; then
  echo "Uso: ./install.sh [--local|--hub]" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker não encontrado. Instale o Docker e rode de novo." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 não disponível." >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL não encontrado; necessário para gerar os segredos." >&2
  exit 1
fi

NOVO_ARQUIVO=0
if [ ! -f .env.docker ]; then
  NOVO_ARQUIVO=1
  echo "Gerando segredos locais…"
  bash ./gerar-segredos.sh
else
  echo ".env.docker existente preservado."
fi

# Compatibilidade com a configuração anterior: migra somente segredos da API
# ausentes, sem executar o conteúdo dos arquivos e sem trocar chaves existentes.
if [ -f .env ]; then
  while IFS= read -r linha || [ -n "$linha" ]; do
    linha="${linha%$'\r'}"
    case "$linha" in
      JWT_SECRET=*|EMBEDDING_KEY=*|ADMIN_SENHA=*)
        chave="${linha%%=*}"
        valor="${linha#*=}"
        if [ -n "$valor" ]; then
          if [ "$NOVO_ARQUIVO" = "1" ]; then
            # Um .env antigo já tem a chave dos dados existentes: ela prevalece
            # sobre o valor recém-gerado, antes de qualquer container iniciar.
            temporario="$(mktemp)"
            awk -F= -v alvo="$chave" '$1 != alvo' .env.docker > "$temporario"
            printf '%s\n' "$linha" >> "$temporario"
            mv "$temporario" .env.docker
          elif ! grep -q "^${chave}=" .env.docker; then
            printf '\n%s\n' "$linha" >> .env.docker
          fi
        fi
        ;;
    esac
  done < .env
else
  touch .env
  echo ".env vazio criado para as opções adicionais da API."
fi
chmod 600 .env.docker .env

if [ "$PERFIL" = "--hub" ]; then
  docker compose -f docker-compose.hub.yml --env-file .env.docker config --quiet
  echo "Baixando imagens do perfil de apresentação…"
  docker compose -f docker-compose.hub.yml --env-file .env.docker pull
  echo "Pronto. Para apresentação: ./astro.sh up"
else
  docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml config --quiet
  echo "Perfil local preparado. Suba com:"
  echo "docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml up -d --build"
fi
