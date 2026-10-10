# Segurança do Astro

Astro é um projeto acadêmico de conta digital PF/PJ. **Não movimenta dinheiro real.**
Mesmo assim é construído e testado como um sistema de pagamentos, e passa por um
pentest feito por outros grupos.

| Documento | Para quê |
|---|---|
| `relatorios/AUDITORIA-2-SEGURANCA.md` | **Auditoria 2 (Claude + Codex)**: achados, correções, revisão cruzada, fuzz de invariantes e concorrência no Postgres |
| `relatorios/` | Relatórios de cada ciclo (C1, C2) e a revisão da lógica bancária (R1) |
| `RELATORIO-10-10-2026.md` | Resumo de tudo o que foi feito em 10/10/2026 |
| `SECURITY_AUDIT.md` | Achados da auditoria, gravidade, evidência, correção, pendências e ações manuais de nuvem |
| `THREAT_MODEL.md` | Ativos, atores, fronteiras de confiança, ameaças e riscos residuais |
| `ACESSO_E_REGRAS_FINANCEIRAS.md` | Autenticação, papéis, alçadas e regras do dinheiro |
| `ENDPOINTS.md` | Inventário das rotas e de quem pode chamar cada uma (gerado do código) |
| `PENTEST.md` | Escopo, regras e modelo de relatório para quem vai testar |
| `SEGURANCA.md` | Histórico dos controles (itens 1–10) e diário |
| `AZURE.md` | Como o ambiente de nuvem é montado |

## 1. Como reportar uma vulnerabilidade

- Durante o pentest: siga `PENTEST.md` (contato, modelo de relatório, o que já sabemos).
- Fora dele: abra um **GitHub Security Advisory privado** no repositório (aba *Security →
  Report a vulnerability*), não uma issue pública.
- Inclua: rota/tela, passo a passo, requisição/resposta (sem tokens válidos nem dados
  pessoais), impacto. Respondemos com: confirmado / duplicado / não reproduzido / fora
  do escopo, e avisamos quando a correção estiver no ambiente para reteste.

## 2. Escopo e limites

- No escopo: app web, API, APK Android e PWA — ver a tabela do `PENTEST.md`.
- Fora: a plataforma de nuvem em si, serviços de terceiros, engenharia social, ataque
  físico, negação de serviço.
- Não use dados reais de terceiros (documento, rosto). Se cair em dado de outra pessoa,
  pare e avise.

## 3. Rodando os testes de segurança localmente

Backend (Python 3.12; `backend/.venv` já criado conforme o `README.md`):

```sh
cd backend
.venv/Scripts/python.exe -m pytest -q                       # suíte inteira (SQLite em memória)
.venv/Scripts/python.exe -m pytest -q tests/test_autorizacao_objetos.py tests/test_pj_regras_bancarias.py \
    tests/test_seguranca_api.py tests/test_forca_bruta.py tests/test_dpop.py tests/test_atestacao.py
.venv/Scripts/python.exe -m pip install pip-audit
PYTHONUTF8=1 .venv/Scripts/python.exe -m pip_audit -r requirements.txt
.venv/Scripts/python.exe scripts/inventario_endpoints.py    # regenera ENDPOINTS.md
```

Concorrência contra Postgres de verdade (lock de linha, idempotência e alçada diária em
paralelo) — precisa de um Postgres vazio:

```sh
TEST_DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/astro_teste \
  .venv/Scripts/python.exe -m pytest -q -rs tests/test_concorrencia_postgres.py
```

No GitHub isso roda sozinho em `.github/workflows/backend.yml` (sobe um Postgres, roda os
testes, sobe/desce as migrações e o `pip-audit`).

App:

```sh
cd app
npx vitest run && npx tsc --noEmit -p . && npm audit --omit=dev
```

Todos os testes usam dados fictícios gerados na hora (CPF/CNPJ válidos aleatórios,
biometria em modo de teste) e banco descartável. Nenhum chama serviço real.

## 4. Princípios que o código segue

- O **servidor** é a única autoridade: identidade, conta, papel, alçada, saldo e valores
  calculados nunca vêm do cliente.
- Segredos só por variável de ambiente (prontos para Key Vault / Secrets Manager);
  produção **não sobe** com segredo fraco, CORS curinga ou modo de teste ligado.
- Nada de detalhe interno em erro; `request_id` em toda resposta e em todo log.
- Toda correção de segurança vem com teste de regressão; nada é dado como corrigido sem ele.
- Credencial que vazar é **rotacionada**, não só apagada do código.
