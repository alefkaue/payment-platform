# ASTRO — plataforma de pagamentos PF/PJ

Banco digital (protótipo acadêmico) para pessoas e empresas, preparado para o **split de IBS/CBS** da
Reforma Tributária (LC 214/2025): a empresa cobra com a nota fiscal e, no pagamento, a CBS e o IBS
destacados na nota são separados e enviados ao Fisco.

> ⚠️ **Protótipo acadêmico / ambiente de simulação** — não movimenta dinheiro real.

## Estrutura do repositório

```
payment-platform/
├── app/          App (React + TypeScript + Vite/TanStack; vira Android via Capacitor)
├── backend/      API FastAPI v9 (Python): contas PF/PJ, cobrança+split, Pix, biometria, limites
├── site/         Site institucional + simulador de split (Next.js)
├── infra/        Infraestrutura: Azure (bicep) e Postgres (papéis de privilégio mínimo)
├── download/     Página de download do APK
├── docs/         Documentação (ver índice abaixo)
├── Dockerfile · docker-compose*.yml · render.yaml · gerar-segredos.sh
└── README.md
```

| Pasta | O que é |
|---|---|
| `backend/` | API FastAPI: `routers/` → `services/` → `repositories/` → `db/` (ver [arquitetura](docs/arquitetura/HANDOFF-V9.md)) |
| `app/` | App Android (Capacitor); a mesma interface sai como app web para testes |
| `site/` | Site institucional com simulador de split (Next.js) |
| `infra/` | Azure Container Apps + ACR + Key Vault (bicep) e init de papéis do Postgres |
| `download/` | Página de download do APK |

## Documentação — índice rápido
- 📘 **Arquitetura & produto:** [`docs/arquitetura/`](docs/arquitetura/) — handoff, plano, endpoints, banco, cadastro, perímetro
- 🔒 **Segurança:** [`docs/seguranca/`](docs/seguranca/) — SECURITY, SEGURANCA, SECURITY_AUDIT, THREAT_MODEL, PENTEST
- ⚙️ **Operação / deploy:** [`docs/operacao/`](docs/operacao/) — AZURE, RODAR-NO-PC, COMO-RODAR-REMOTO
- 🤖 **Colaboração com IAs:** [`docs/ia/`](docs/ia/)
- 🗂️ **Histórico (relatórios/revisões datados):** [`docs/historico/`](docs/historico/)
- 🔎 **Auditoria (conselho de personas):** [`docs/auditoria-personas/`](docs/auditoria-personas/)

Índice detalhado em [`docs/README.md`](docs/README.md).

## Como rodar

**Backend (demo local, SQLite, biometria em modo de teste):**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv/Scripts/activate
pip install -r requirements.txt
BIOMETRIA_STUB=1 uvicorn app.main:app --reload       # Swagger em http://127.0.0.1:8000/docs
python -m pytest                                     # testes
```
`BIOMETRIA_STUB=1` aprova qualquer rosto: só para demo, **nunca no pentest**.

**App:**
```bash
cd app
npm install
npm run dev                                          # http://localhost:8081
```
Sem `VITE_API_URL`, o app roda em **modo demonstração** (mocks). Para usar o backend, crie `app/.env`
com `VITE_API_URL=http://localhost:8000`.

**Stack completo a partir do código local (app, API e PostgreSQL):**

Com `.env` e `.env.docker` configurados, execute:

```bash
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml up -d --build
```

App em `http://localhost:8080`; API em `http://localhost:8000`. Este perfil mantém
DPoP e biometria real ligados, valida os modelos faciais como o usuário do container
e espera API/banco saudáveis. O frontend usa a API, sem os mocks do app.
O banco mantém o volume existente e não publica porta no host.

Para ver o estado e parar sem apagar dados:

```bash
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml ps -a
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml down
```

Este é o perfil local: produção exige HTTPS e a configuração do ambiente de
implantação. Não confunda esta execução com a publicação de imagens no Docker Hub
ou com o deploy Azure.

**Jeito fácil (3 containers via Docker Hub) — recomendado:**
```bash
./install.sh     # uma vez: checa Docker, gera segredos, baixa as imagens
./astro.sh       # painel: subir, parar, logs, status, testes, limpar…
# ou direto:  ./astro.sh up   →  app http://localhost:8080 · api http://localhost:8000
```
O painel `./astro.sh` aceita comandos: `up`, `down`, `restart`, `status`, `logs [api|app|db]`, `open`,
`test`, `clean`, `help`.

O `docker-compose.yml` (build local, backend + Postgres + migração com credenciais separadas) também
está disponível. Detalhes do banco em [`docs/arquitetura/BANCO.md`](docs/arquitetura/BANCO.md).

## Regras principais
- **Split só no PJ**, e só no pagamento de **cobrança com nota fiscal** (transferência **nunca** retém imposto). Benefícios PF (loja/viagens/pontos) estão arquivados (`BENEFICIOS_HABILITADOS=0`).
- **Transição honesta** (LC 214/2025): 2026 é ano-teste — a cobrança mostra o imposto destacado, mas a empresa recebe o valor inteiro; a retenção começa em `SPLIT_RETENCAO_DESDE` (padrão 2027-01-01). Alíquotas seguem a transição 2026–2033.
- Login é da **pessoa**; empresas são operadas por **vínculo** (papel + alçada), com **dupla aprovação** acima da alçada.
- Limites diurno/noturno, regra de **aparelho novo** (BCB), bloqueio cautelar e contestação (MED) rodam no servidor.
- Dinheiro trafega como **string decimal** (`"1500.00"`). **Idempotência** nos fluxos de pagamento.
- Segurança e auditoria: [`docs/seguranca/SECURITY.md`](docs/seguranca/SECURITY.md) · regras do pentest em [`docs/seguranca/PENTEST.md`](docs/seguranca/PENTEST.md).
