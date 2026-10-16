# Handoff — frontend precisa casar com senha/TOTP (prompt #2/#4)

O **backend já migrou**: reconhecimento facial foi **removido de todos os pagamentos** e trocado por
**senha** (sempre) **+ TOTP** acima de `LIMITE_AUTENTICACAO_ADICIONAL` (padrão **R$ 5.000,00**). Facial
continua só em **login/cadastro** (não é pagamento). Ver
[PAGAMENTO-SENHA-TOTP-E-ATIVACAO-IMEDIATA.md](PAGAMENTO-SENHA-TOTP-E-ATIVACAO-IMEDIATA.md).

> ⚠️ **Deploy:** o servidor já **espera** senha/TOTP. Se subir o backend sem atualizar o `app/`, a tela de
> transferência (e as outras) **quebra** (app manda rosto, backend quer senha). Como o repo sobe os dois
> juntos, **termine o front antes do próximo deploy.** Backend na main: suíte **711 passed**.

## O que o backend agora espera (contrato)
Todos os endpoints de pagamento aceitam no corpo:
- `senha`: senha da conta (string). **Obrigatória** — sem ela → **401**.
- `codigo_totp`: código de 6 dígitos do app autenticador. Exigido quando `valor > 5000` (ou aprovação de
  acesso). Sem TOTP ativo e acima do limite → **403** ("Ative a verificação em duas etapas..."). Código
  errado/reutilizado → **401**.

Campos `biometria`/`prova` **foram removidos** dos schemas de pagamento (ignorados se enviados).

Endpoints afetados: `POST /pagamentos/transferir`, `/pagamentos/lote`,
`/cobrancas/{txid}/pagar`, `/empresas/atual/folha/pagar`, `/pagamentos/pendentes/{id}/decidir`,
`/pagamentos/pendentes/{id}/repetir`, `/pagamentos/transacoes/{id}/devolver`,
`/loja/produtos/{id}/comprar`, `/viagens/voos/{id}/comprar`.

## Ativação do TOTP (novo)
- `GET /auth/eu` passou a devolver `tem_totp` (bool).
- `POST /auth/totp` → `{segredo, uri}` (uri `otpauth://` pra QR Code). Começa a ativação.
- `POST /auth/totp/confirmar` `{codigo}` → 204 confirma (ou 400 se o código não bate).

## O que falta no `app/` (TanStack + Vite + Capacitor, bun)
1. **`src/lib/api.ts`** — funções trocarem a prova facial por `senha`/`codigo_totp` no corpo:
   `transferir` (~914), `pagarCobranca` (~960), `comprarProduto` (~1712), `comprarPassagem` (~1760),
   `decidirPendente` (~2264), `pagarFolha` (~2446) e a de devolver. Vale tanto o ramo real quanto o **modo
   demo** (simulação offline em TS, em `src/lib/`) — a simulação precisa espelhar a regra senha/TOTP.
2. **Telas** (`src/routes/`): `_app.transferir.tsx`, `_app.folha.tsx`, `_app.pendentes.tsx`, loja/viagens,
   devolução — pedir **senha** na confirmação e **código TOTP** quando o valor passar do limite, no lugar da
   captura facial (`components/payflow/liveness.tsx`, `lib/captura-facial.ts`).
3. **Tela de ativar TOTP** (sugestão: em `_app.seguranca.tsx` ou `_app.config.tsx`): mostra QR do
   `uri`/`segredo` de `POST /auth/totp` e confirma com `POST /auth/totp/confirmar`. Usar `tem_totp` do
   `/auth/eu` pra indicar status.
4. **Testes** (~45 arquivos em `src/lib/*.test.ts`): vários afirmam a regra **antiga** ("pede rosto acima de
   500" — ex. `folha.test.ts`, `demo.test.ts`, `contestacao-estorno.test.ts`, `senha.test.ts`). Atualizar
   para senha/TOTP.

## Como rodar os testes
- **Backend:** `docker run --rm --entrypoint sh -v "$PWD/backend:/src:ro" matheussousaavelino/payment-platform-api:latest -c "mkdir -p /tmp/b && cp -r /src/. /tmp/b/ && cd /tmp/b && python -m pytest -q -p no:cacheprovider --ignore=tests/test_instalacao_containers.py"`
- **Frontend:** `cd app && bun install && bun run test` (`vitest`). Em **Node ≥ 26** o `localStorage` do
  jsdom é sombreado por um global nativo → rode `NODE_OPTIONS="--localstorage-file=/tmp/ls.json" bun run test --no-file-parallelism`. Baseline atual (sem mexer): **282 passed**.
  Build/lint: `bun run build`, `bun run lint`.

## Status (16/10/2026): frontend concluído
- `src/lib/api.ts`: pagamentos mandam `senha`/`codigo_totp` (`ConfirmacaoPagamento` em `types.ts`), sem
  `biometria`. Recusar uma pendência não pede nada. Novos `temTotp`, `iniciarTotp`, `confirmarTotp`,
  `pedeTotp`, `aprovacaoPedeTotp`, `repeticaoPedeTotp` e `LIMITE_AUTENTICACAO_ADICIONAL` (5000).
- **Modo demo** espelha a regra: senha da pessoa (hash do banco demo), TOTP RFC 6238 real
  (`src/lib/totp.ts`), anti-replay por passo. O segredo TOTP da demo fica só no `localStorage` do aparelho.
- **Telas**: `components/payflow/confirmar-pagamento.tsx` (senha + código; se o servidor pedir o 2º fator,
  a janela passa a pedir) em transferir/cobrança, folha e aprovações. Ativação com QR Code em
  **Segurança** (`components/payflow/ativar-totp.tsx`, lib `uqr`).
- **Testes**: 295 passando (`npx vitest run`, eram 282), mais `api.e2e.test.ts` (3) contra o backend local com
  `BIOMETRIA_STUB=1 DEPOSITO_DEMO=1`, incluindo ativar TOTP e pagar R$ 5.000,01.
- Não havia tela de devolução de Pix nem Loja/Viagens ativas no app (estão arquivadas); a API já manda a
  confirmação nas compras.
