#!/usr/bin/env bash
# Instalação em 1 comando do stack ASTRO (3 containers do Docker Hub).
# Uso:  ./install.sh
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "🚀  ASTRO — instalação do ambiente"
echo "=================================================="

# 1. Docker presente?
if ! command -v docker >/dev/null 2>&1; then
  echo "❌  Docker não encontrado. Instale o Docker e rode de novo."
  echo "    Arch: sudo pacman -S docker docker-compose && sudo systemctl enable --now docker"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "❌  'docker compose' (v2) não disponível. Atualize o Docker."
  exit 1
fi
echo "✅  Docker: $(docker --version | awk '{print $3}' | tr -d ,)"

# 2. Segredos de teste (gera se faltarem)
if [ ! -f .env.docker ]; then
  echo "🔐  Gerando segredos de teste (.env.docker)…"
  bash ./gerar-segredos.sh
else
  echo "🔐  .env.docker já existe — mantido."
fi
# .env é exigido pelo compose do time (perfil seguro full.yml). Os segredos ficam
# no .env.docker; este fica vazio só para o Compose encontrar o arquivo.
[ -f .env ] || { touch .env; echo "📄  .env vazio criado (exigido pelo perfil seguro)."; }

# 3. Baixar as imagens do Docker Hub
echo "📦  Baixando as imagens (app, api, db) do Docker Hub…"
docker compose -f docker-compose.hub.yml --env-file .env.docker pull

echo ""
echo "=================================================="
echo "✅  Pronto! Agora use o painel:   ./astro.sh"
echo "    Ou direto:  ./astro.sh up   →  app http://localhost:8080"
echo "=================================================="
