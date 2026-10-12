#!/usr/bin/env bash
# Painel ("hub") do ASTRO — sobe/para o stack, mostra logs, status, testes.
# Uso:
#   ./astro.sh            menu interativo
#   ./astro.sh up|down|restart|status|logs|logs api|open|test|clean|help
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose -f docker-compose.hub.yml --env-file .env.docker)
APP_URL="http://localhost:8080"
API_URL="http://localhost:8000"

cor()   { printf "\033[%sm%s\033[0m" "$1" "$2"; }
titulo(){ echo; cor "1;36" "── $* ──"; echo; }
erro()  { cor "1;31" "❌ $*"; echo; }

checar() {
  if [ ! -f .env.docker ]; then
    erro "Falta o .env.docker. Rode primeiro:  ./install.sh"
    exit 1
  fi
}

up()      { checar; titulo "Subindo os 3 containers"; "${COMPOSE[@]}" up -d && echo "✅  app: $APP_URL   api: $API_URL"; }
down()    { titulo "Parando (mantém o banco)";        "${COMPOSE[@]}" down; }
restart() { down; up; }
status()  { titulo "Status";                          "${COMPOSE[@]}" ps; }
clean()   { titulo "Apagando tudo (containers + volume do banco)"; "${COMPOSE[@]}" down -v && echo "🧹  limpo."; }
open_app(){ titulo "Abrindo o app"; if command -v xdg-open >/dev/null 2>&1; then xdg-open "$APP_URL" >/dev/null 2>&1 & else echo "Abra no navegador: $APP_URL"; fi; }

logs() {
  local svc="${1:-}"
  titulo "Logs ${svc:-(todos)} — Ctrl+C para sair"
  if [ -n "$svc" ]; then "${COMPOSE[@]}" logs -f "$svc"; else "${COMPOSE[@]}" logs -f; fi
}

test_backend() {
  titulo "Testes do backend"
  if [ -x backend/.venv/bin/pytest ]; then
    (cd backend && BIOMETRIA_STUB=1 .venv/bin/python -m pytest -q)
  elif command -v python >/dev/null 2>&1 && [ -d backend/.venv ]; then
    (cd backend && BIOMETRIA_STUB=1 .venv/bin/python -m pytest -q)
  else
    erro "Ambiente de testes não encontrado em backend/.venv"
    echo "   Prepare uma vez:  cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  fi
}

ajuda() {
  cat <<EOF
Painel ASTRO — comandos:
  up        sobe os 3 containers (app, api, db)
  down      para (mantém o banco)
  restart   reinicia
  status    mostra o status dos containers
  logs [s]  acompanha os logs (s = api | app | db | migrate; vazio = todos)
  open      abre o app no navegador ($APP_URL)
  test      roda os testes do backend (precisa de backend/.venv)
  clean     apaga containers + volume do banco
  help      esta ajuda
Sem argumento, abre o menu interativo.
EOF
}

menu() {
  while true; do
    echo
    cor "1;35" "========== PAINEL ASTRO =========="; echo
    echo "  1) Instalar / preparar (gera segredos + baixa imagens)"
    echo "  2) Subir os containers        (up)"
    echo "  3) Parar                      (down)"
    echo "  4) Reiniciar                  (restart)"
    echo "  5) Status                     (ps)"
    echo "  6) Ver logs"
    echo "  7) Abrir o app no navegador"
    echo "  8) Rodar testes do backend"
    echo "  9) Limpar tudo (apaga o banco)"
    echo "  0) Sair"
    printf "Escolha: "; read -r op
    case "$op" in
      1) bash ./install.sh --hub ;;
      2) up ;;
      3) down ;;
      4) restart ;;
      5) status ;;
      6) printf "Qual serviço? (api/app/db/migrate, vazio=todos): "; read -r s; logs "$s" ;;
      7) open_app ;;
      8) test_backend ;;
      9) clean ;;
      0|q|sair) echo "👋"; exit 0 ;;
      *) erro "Opção inválida." ;;
    esac
  done
}

case "${1:-}" in
  "")        menu ;;
  up)        up ;;
  down)      down ;;
  restart)   restart ;;
  status|ps) status ;;
  logs)      logs "${2:-}" ;;
  open)      open_app ;;
  test|tests|testes) test_backend ;;
  clean)     clean ;;
  help|-h|--help) ajuda ;;
  *) erro "Comando desconhecido: $1"; ajuda; exit 1 ;;
esac
