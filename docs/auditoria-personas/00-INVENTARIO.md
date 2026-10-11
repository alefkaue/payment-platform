# 00 — Inventário neutro de funcionalidades (base da auditoria)

> Base **neutra** para os subagentes. Sem juízo de valor — apenas o que existe e seu estado.
> Legenda de estado: **IMPLEMENTADA** (endpoint/tela presente e com lógica) · **PARCIAL** (existe, cobertura/limite a confirmar) · **MOCK/DEMO** (depende de modo de teste) · **NÃO EXISTE** · **NÃO VERIFICADA** (presente, profundidade não auditada nesta fase).

- **Repositório:** `alefkaue/payment-platform`
- **Branch:** `main`
- **Commit de referência:** `289effbad5d858908a0cdf9546711320e898c00d`
- **Working tree:** limpo na captura (`git status --short` vazio)
- **Versão declarada pela API:** `/` responde `servico: astro, versao: 9.0, modo: simulacao, dinheiro_real: false`
- **Data da captura:** 2026-10-11

## Camadas do código (fato)

| Camada | Local | Conteúdo |
|---|---|---|
| Backend | `backend/app/` | FastAPI; `routers/` (9), `services/` (24), `repositories/`, `db/models.py` (32 tabelas), `core/` (18 módulos), `deps.py` |
| Frontend | `app/src/` | React + TS + Vite/TanStack; 24 telas em `routes/`, `lib/` (http/api/auth), `components/`, `mocks/` (`data.ts`, `banco.ts`) |
| Site | `site/` | Next.js institucional + simulador de split |
| Infra | `infra/`, `*Dockerfile`, `docker-compose*.yml`, `render.yaml` | Postgres com papéis de privilégio mínimo, Azure (bicep), Render |
| Testes | `backend/tests/` (53 arquivos / 448 funções), `app/src/**/*.test.ts*` (43) | pytest + Vitest |

## Backend — routers registrados (`main.py`)
`auth`, `contas`, `identidade`, `biometria`, `pagamentos`, `cobrancas`, `beneficios`, `seguranca`, `admin` (ordem de `include_router`).

## Funcionalidades por domínio (estado inicial — a refinar na Fase 1)

| Domínio | Evidência (arquivo) | Estado inicial |
|---|---|---|
| Autenticação PF (senha + MFA/rosto + TOTP) | `routers/auth.py` (`/login`, `/login/mfa`, `/login/totp`, `/login/mfa/desafio`) | IMPLEMENTADA |
| Refresh / logout / sessões | `auth.py` (`/refresh`, `/logout`, `/sessoes`, `/sessoes/encerrar-outras`) | IMPLEMENTADA |
| Recuperação de senha | `auth.py` (`/recuperacao`, `/recuperacao/concluir`), `core/senha_policy` | IMPLEMENTADA |
| Cadastro PF / sessão de cadastro | `routers/contas.py` (`/usuarios`, `/usuarios/cadastro-sessao`) | IMPLEMENTADA |
| Conta/empresa PJ, vínculos, políticas | `contas.py` (`/empresas`, `/empresas/atual/vinculos`, `.../politica`), `services/politica_pj.py`, `equipe_service.py` | IMPLEMENTADA |
| KYC/KYB, documentos PF/PJ | `routers/identidade.py`, `services/documento_service.py`, `ocr_service.py`; tabelas `kyc_casos`, `documentos_*` | PARCIAL (OCR ≠ autenticidade — validar) |
| Biometria facial / liveness / atestação | `routers/biometria.py`, `services/face_engine.py`, `liveness_logic.py`, `landmarks_service.py`, `qualidade_rosto.py`, `core/atestacao.py` | IMPLEMENTADA (real `opencv`; `BIOMETRIA_STUB` em teste) |
| Transferência / lote / idempotência | `routers/pagamentos.py` (`/transferir`, `/lote`), `deps.chave_idempotencia`, `services/pagamento_service.py` | IMPLEMENTADA |
| Devolução / contestação (MED) | `pagamentos.py` (`/transacoes/{id}/devolver`, `/contestar`); tabela `contestacoes` | IMPLEMENTADA |
| Operações pendentes (maker-checker) | `pagamentos.py` (`/pendentes/{id}/decidir`); tabela `operacoes_pendentes` | IMPLEMENTADA |
| Split IBS/CBS (simulação + transição) | `pagamentos.py` (`/split/simular`, `/split/transicao`), `services/split_service.py`, `tributos_service.py` | IMPLEMENTADA (simulação) |
| Depósito demo | `pagamentos.py` (`/depositar-demo`), `config.DEPOSITO_DEMO` | MOCK/DEMO |
| Cobrança + NF-e / cancelar / estornar | `routers/cobrancas.py`; `services/cobranca_service.py`; chave 44 dígitos | IMPLEMENTADA (validação estrutural ≠ consulta oficial) |
| Pix Automático (autorizações recorrentes) | `cobrancas.py` (`/pix-automatico/...`); tabela `autorizacoes_recorrentes` | IMPLEMENTADA |
| Chaves Pix / consulta | `routers/seguranca.py` (`/pix/chaves`, `/pix/consultar/{chave}`) | IMPLEMENTADA |
| Limites / dispositivos / confiar/bloquear | `seguranca.py` (`/seguranca/limites`, `/seguranca/dispositivos/...`) | IMPLEMENTADA |
| Auditoria da empresa / atividade | `seguranca.py` (`/empresas/atual/auditoria`, `/seguranca/atividade`); tabela `logs_auditoria` | IMPLEMENTADA |
| Tributos / créditos / webhooks | `seguranca.py` (`/empresas/atual/tributos`, `.../creditos`, `.../webhooks`), `services/webhook_service.py` | IMPLEMENTADA |
| Rendimento | `seguranca.py` (`/rendimento`), `services/rendimento_service.py`; tabela `rendimentos` | NÃO VERIFICADA |
| Folha de pagamento | `services/folha_service.py`; tela `_app.folha.tsx`; tabela `funcionarios` | PARCIAL |
| Benefícios PF (loja/viagens/pontos) | `routers/beneficios.py`; tabelas `produtos`, `voos`, `pontos_movimentos` | NÃO VERIFICADA (`BENEFICIOS_HABILITADOS=0` em produção) |
| Cartões | tela `_app.cartoes.tsx`; tabela `cartoes` | NÃO VERIFICADA |
| Convites de equipe | tela `_app.convites.tsx`; `equipe_service.py` | IMPLEMENTADA |

## Segurança/infra (camadas presentes — fato)
- **DPoP** (`core/dpop.py`, tabela `dpop_jtis`, `deps` com `X-Dispositivo-Id`), **atestação de aparelho** (`core/atestacao.py`).
- **Cifragem de dados pessoais/PII** (`core/dados_pessoais.py`, `db/dados_cifrados.py`), **cifragem de webhooks** (`core/segredos_webhook.py`).
- **Isolamento multi-tenant / RLS** (`db/isolamento.py`, `permissoes.py`, `seguranca_runtime.py`) — papéis `astro_app`/`astro_migrator`.
- **Perímetro/rotas** (`core/perimetro.py`, `rotas.py`), **TOTP admin** (`core/totp.py`), **limites** (`core/limites.py`).

## Modo demonstração × produção (fato)
- Front: `app/src/lib/http.ts` — `MODO_API = Boolean(VITE_API_URL)`; sem a variável, usa mocks (`src/mocks/`).
- Back: `AMBIENTE=producao` ativa validações rígidas (TLS no banco `sslmode=verify-full`, CORS/DPoP HTTPS, segredos obrigatórios) — ver `core/config.py:_conferir_producao`. `BIOMETRIA_STUB`/`DEPOSITO_DEMO`/`CNPJ_PROVEDOR=stub` são **proibidos em produção** por validação de boot.

## Limitações desta base
- Estados "NÃO VERIFICADA/PARCIAL" exigem leitura dirigida na Fase 1.
- Números de teste (448/43) são contagem estática, **não** execução — rodar é tarefa da Fase 2 quando o ambiente permitir.
- Nenhuma conclusão de valor aqui; juízos ficam nos relatórios dos subagentes.
