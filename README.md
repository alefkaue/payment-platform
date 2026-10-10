# ASTRO

Banco digital para pessoas e empresas, preparado para o **split de IBS/CBS** da
Reforma Tributária (LC 214/2025): a empresa cobra com a nota fiscal e, no
pagamento, a CBS e o IBS destacados na nota são separados e enviados ao Fisco.

> Estado do projeto, decisões e próximos passos: **[HANDOFF.md](HANDOFF.md)**.
> Plano de produto: [PLANO.md](PLANO.md).

## Pastas

| Pasta | O que é |
|---|---|
| `backend/` | API FastAPI v7 (Python): contas PF/PJ, cobrança com split, Pix, limites, biometria |
| `app/` | App web + Android (Vite, TanStack, React, Capacitor) |
| `site/` | Site institucional com simulador de split (Next.js) |

## Rodar rápido

**Backend** (SQLite local, biometria em modo de teste):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
BIOMETRIA_STUB=1 uvicorn app.main:app --reload     # Swagger em http://127.0.0.1:8000/docs
python -m pytest                                    # testes
```

No PowerShell, defina a variável antes: `$env:BIOMETRIA_STUB="1"`.
Admin de desenvolvimento: `admin@payflow.com.br` / `payflow-admin-dev`.

**App**:

```bash
cd app
npm install
npm run dev                        # http://localhost:8081
```

Sem `VITE_API_URL` o app roda em **modo demonstração** (dados fictícios). Para usar o
backend, crie `app/.env` com `VITE_API_URL=http://localhost:8000`.

**Docker (backend + Postgres)**: copie `.env.example` para `.env` e
`.env.docker.example` para `.env.docker`, preencha os segredos e rode
`docker compose --env-file .env.docker up --build`. Banco, migração e API têm
credenciais separadas. Veja [estrutura e operação do banco](docs/BANCO.md).

Sem permissão de administrador para instalar o Node? Veja a seção "Node sem
administrador" no [HANDOFF.md](HANDOFF.md#node-sem-administrador).

## Regras principais

- **PF tem Loja, Viagens e pontos** (1 ponto por real; passagens resgatadas com pontos). **PJ tem o split.**
- **Transferência nunca tem imposto retido.** O split só acontece no pagamento de
  uma **cobrança com nota fiscal**, e só para empresas do regime regular.
- Alíquotas seguem a **transição** 2026–2033 (2026: CBS 0,9% + IBS 0,1%; IBS
  pleno só em 2033). O banco retém o que **a nota** diz.
- Login é da **pessoa**; empresas são operadas por vínculo (papel + alçada), com
  **dupla aprovação** acima da alçada.
- Limites diurno/noturno, regra de **aparelho novo** do Banco Central, bloqueio
  cautelar e contestação (MED) rodam no servidor.
- Dinheiro trafega como **string decimal** (`"1500.00"`).
