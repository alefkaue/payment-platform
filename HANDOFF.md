# PayFlow — Handoff (para continuar o trabalho)

Documento de passagem de bastão: o que já foi feito, como rodar, as decisões
tomadas e **o que falta**. Complementa o `PLANO.md` (plano de produto).
Última atualização: 2026-10-06 (backend v7 + app ligado ao backend).

---

## 1. O que é o projeto

**PayFlow** — banco digital brasileiro cujo diferencial é o **split de IBS/CBS da
Reforma Tributária** resolvido no ato do pagamento. Foco de venda: **empresas**
(split + créditos tributários), mas também atende **PF**. Vai ser apresentado para
Mercedes e Scania.

## 2. Estrutura do repositório (monorepo)

```
app/        # App (web Vite + TanStack Router, TypeScript) + empacotamento mobile Capacitor (android/)
site/       # Vitrine institucional (Next.js 15 + React 19, TypeScript)
backend/    # API FastAPI v7 (pessoa/empresa/vínculo, split por NF-e, limites, Pix Automático...)
.github/workflows/android.yml  # CI que gera o .apk na nuvem
PLANO.md    # plano de produto
HANDOFF.md  # este arquivo
```

## 3. Como rodar

- **Backend (sem Docker):**
  ```bash
  cd backend
  python -m venv .venv && .venv/Scripts/activate      # Linux/Mac: source .venv/bin/activate
  pip install -r requirements.txt                       # pesado (DeepFace/TensorFlow)
  # Para só testar a lógica sem TensorFlow, instale o que os testes usam:
  # pip install fastapi pydantic-settings email-validator "passlib[bcrypt]==1.7.4" bcrypt==4.0.1 PyJWT cryptography sqlalchemy alembic httpx pytest
  BIOMETRIA_STUB=1 uvicorn app.main:app --reload        # SQLite local (payflow.db), Swagger em /docs
  ```
  Admin de desenvolvimento: `admin@payflow.com.br` / `payflow-admin-dev` (só quando
  `ADMIN_SENHA` não está definida e `AMBIENTE` não é produção).
- **Backend (Docker):** `cp .env.example .env`, preencha `POSTGRES_PASSWORD` e os
  segredos, `docker compose up --build`. O `entrypoint.sh` roda `alembic upgrade head`.
- **Testes do backend:** `cd backend && python -m pytest` (SQLite em memória,
  `BIOMETRIA_STUB`, sem rede). **92 testes passando** em 2026-10-06.
- **App (web):** `cd app && npm install && npm run dev` → http://localhost:8081.
  - Sem `VITE_API_URL`: **modo demonstração** (mocks, qualquer login entra).
  - Com `VITE_API_URL=http://localhost:8000` em `app/.env`: fala com o backend.
- **Site:** `cd site && npm install && npx next dev -p 8090`.
- **Type-check:** `npx tsc --noEmit` em `app/` e `site/`. Testes do app: `cd app && npm test`.
- **Teste ponta a ponta app ↔ backend** (`app/src/lib/api.e2e.test.ts`, pulado sem a variável):
  backend com `BIOMETRIA_STUB=1 uvicorn app.main:app --port 8765` e, no app,
  `VITE_API_URL=http://localhost:8765 npx vitest run src/lib/api.e2e.test.ts`. Passou em 2026-10-06.

### Node sem administrador

PC da faculdade sem permissão de admin: use o Node **portátil** (zip), sem instalar.
No PowerShell:

```powershell
cd $env:USERPROFILE
Invoke-WebRequest https://nodejs.org/dist/v22.20.0/node-v22.20.0-win-x64.zip -OutFile node.zip
Expand-Archive node.zip -DestinationPath .
$env:Path = "$env:USERPROFILE\node-v22.20.0-win-x64;$env:Path"   # vale só nesta janela
node --version
```

Python: o `py`/`python` do Windows já existe nos PCs da faculdade; o venv
(`python -m venv .venv`) também não precisa de admin.

### Gotchas de ambiente
- `app/` usa **strict tsc** (`exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`,
  `noPropertyAccessFromIndexSignature`).
- `app/` é TanStack Start com **modo SPA** (`vite.config.ts` → `tanstackStart.spa.enabled`).
- `site/` está em **Next 15 / React 19** e **TypeScript 5.x** (TS 7 não é suportado).
- Windows: o `zoneinfo` do Python não tem fusos sem o pacote `tzdata`; por isso o
  backend usa deslocamento fixo de -3h para Brasília (`app/core/tempo.py`).

---

## 4. Backend v7 — o que mudou e por quê

A revisão de 2026-10-06 (comparando com Nubank, Inter, C6 e com a LC 214/2025)
achou problemas de conceito no split e lacunas de banco PJ. A v7 corrige.

### 4.1 Split (Reforma Tributária) — `services/split_service.py`, `services/cobranca_service.py`
- **Transferência nunca retém imposto.** Na v6 qualquer Pix para PJ perdia CBS/IBS
  (sócio → empresa, reembolso, empréstimo). Agora o split só acontece no
  **pagamento de cobrança com nota fiscal**.
- **O banco retém o imposto destacado na nota**, não recalcula: a cobrança traz a
  chave de acesso (44 dígitos, DV conferido, CNPJ do emitente = CNPJ da empresa) e
  os valores de CBS e IBS da nota. A redução por setor vale por produto/serviço
  (NCM/NBS), e quem calcula isso é a nota.
- **Tabela de transição corrigida** (`CRONOGRAMA`): 2026 CBS 0,9% + IBS 0,1%;
  2027–2028 CBS cheia + IBS 0,1%; IBS sobe 10/20/30/40% da referência em
  2029–2032; pleno em 2033. A v6 usava IBS de 17,7% já em 2027. As alíquotas de
  referência (CBS 8,8% / IBS 17,7%) ainda são estimativas — ajuste quando saírem
  as oficiais. A EC prevê redução de 0,1 p.p. na CBS em 2027–2028: conferir.
- `estimar()` é só para o simulador (`GET /pagamentos/split/simular`), com regime
  do setor; `GET /pagamentos/split/transicao` devolve a tabela.
- **Regime de apuração da empresa:** `regular` retém; `simples` e `mei` não.
- **Modo "inteligente"**: retém o bruto da nota. O abatimento de crédito em tempo
  real ("superinteligente") depende da plataforma da Receita/CGIBS, sem padrão
  técnico ainda. A "restituição prevista" em `/empresas/atual/tributos` é estimativa.
- **Créditos são informação** (`creditos_tributarios`: valor, fonte, data), não
  dinheiro do banco. Fontes: `declarado`, `estorno`, futuro `plataforma_publica`.
- **Contas de sistema separadas** (antes a conta "Governo" era admin + emissor +
  destino do imposto): `CAIXA` (depósitos e rendimento; pode ficar negativa),
  `TRIBUTOS` (transitória) e `FISCO` (destino do repasse). Admin agora é uma
  pessoa com papel `admin`, sem carteira.
- **Repasse D+1**: `POST /admin/tributos/repassar` leva ao FISCO o que foi retido
  antes do início do dia.
- **Estorno de cobrança**: devolve o bruto ao pagador. Tributo ainda não repassado
  volta da conta TRIBUTOS; o já repassado sai do recebedor e vira crédito `estorno`.
- **Parcelamento**: N cobranças com valor/CBS/IBS proporcionais, a última absorve
  os centavos.

### 4.2 Pessoa x empresa x vínculo — `services/contas_service.py`, `deps.py`
- `usuarios` = pessoa (CPF obrigatório e validado, login, biometria).
  `empresas` = CNPJ, porte, regime. `vinculos` = pessoa↔empresa com papel
  (`admin`, `aprovador`, `operador`, `consulta`) e **alçada** em R$.
- **Login é sempre da pessoa.** Para operar uma empresa, o app manda o header
  `X-Conta: <número da conta PJ>`. `GET /auth/eu` e `GET /contas` listam as contas
  que a pessoa pode operar.
- **Abertura de empresa** (`POST /empresas`): CNPJ com DV válido, consulta no
  provedor (`CNPJ_PROVEDOR=stub|brasilapi`), situação ATIVA e, se o provedor traz
  o quadro de sócios, o CPF de quem abre precisa estar nele. `stub` é proibido em produção.
- **Dupla aprovação**: operação acima da alçada de quem lançou vira
  `operacoes_pendentes` (HTTP 202). Outra pessoa com papel `admin`/`aprovador` e
  alçada suficiente decide em `POST /pagamentos/pendentes/{id}/decidir`.
- A empresa nunca fica sem pelo menos um `admin`.

### 4.3 Segurança — `services/seguranca_service.py`, `services/biometria_service.py`
- **Aparelho** (`X-Dispositivo-Id`, obrigatório para movimentar dinheiro).
  Aparelho novo de PF: **R$ 200/transação e R$ 1.000/dia** (IN BCB 491/2024) até
  ser confirmado com verificação facial (`POST /seguranca/dispositivos/atual/confiar`).
  O aparelho usado no cadastro já nasce confiável.
- **Limites no servidor** (por transação, diurno, noturno 20h–6h). Reduzir vale na
  hora; aumentar só depois de 24h (`LIMITE_CARENCIA_HORAS`). As checagens rodam
  dentro do lock da carteira, junto com o débito.
- **Prova de vida decidida pelo servidor**: `POST /biometria/desafios` sorteia uma
  ação (virar à esquerda/direita) com validade e uso único; o app manda 2–5
  quadros; o servidor confere o desafio, faz anti-spoofing em todos, mede o giro
  da cabeça e compara o rosto. O desafio de MFA precisa ter sido pedido pela mesma
  pessoa logada. **Calibrar `GIRO_MINIMO`/sinal num aparelho real** (ver docstring).
- A análise facial roda num semáforo (`BIOMETRIA_CONCORRENCIA`); excesso → 503.
- **Bloqueio cautelar**: transferência ≥ R$ 1.000 para destino novo fica retida no
  recebedor (`saldo_bloqueado`) por até 72h. Job libera; admin pode liberar antes.
- **Contestação (MED)**: `POST /pagamentos/transacoes/{id}/contestar` (até 80 dias);
  admin decide; procedente devolve primeiro do bloqueado, depois do saldo livre.
- **Login**: rate limit por e-mail **e por IP**; `X-Forwarded-For` só é lido de
  proxies em `PROXIES_CONFIAVEIS`. A senha de admin de dev saiu do log.
- **Idempotência por conta**: na v6 a chave era global — outra pessoa que repetisse
  a chave recebia a transação alheia.

### 4.4 Engenharia
- **Chaves Pix** (`cpf`, `cnpj`, `email`, `celular`, `aleatoria`; 5 por PF, 20 por
  PJ). Consulta devolve nome/documento mascarados e tem limite por hora.
  Contas têm agência `0001` + número com dígito gerado pelo banco (acabou o id de
  6 dígitos escolhido pelo usuário). E-mail/celular ainda **sem confirmação por código** (TODO).
- **Dinheiro como string** em toda a API (`"1500.00"`), inclusive endpoints sem
  `response_model` (`main.py` troca o encoder de `Decimal`).
- **Migração Alembic `c7a1e0f2b3d4` é DESTRUTIVA** (apaga as tabelas v6 e cria a
  v7). Testada em SQLite (upgrade + `alembic check` limpo). **Não testada em Postgres.**
- `docker-compose.yml` lê credenciais do `.env` (sem senha fixa).

### 4.5 Produtos PJ novos
- **Cobrança** Pix (txid) + boleto: `POST /cobrancas`, pagar, cancelar, estornar.
  Pix copia-e-cola e linha digitável são **simulados** (emitir de verdade exige
  SPI/DICT ou parceiro, e convênio de boleto).
- **Pix Automático**: empresa pede autorização (valor máximo + periodicidade),
  pagador aceita, empresa gera uma cobrança por período, `POST /admin/jobs/recorrencias`
  paga as vencidas. Pagador cancela quando quiser.
- **Pagamento em lote**: `POST /pagamentos/lote` (até 100 itens, uma biometria
  para o lote, resultado por item).
- **Webhooks** (`cobranca.paga`, `cobranca.estornada`, `pix.recebido`,
  `operacao.pendente`), assinados com HMAC-SHA256 (`X-PayFlow-Assinatura`),
  reenvio por `POST /admin/jobs/webhooks`.
- **Rendimento diário** (CDI × percentual, dias úteis, idempotente):
  `POST /admin/jobs/rendimento`. Sem IR/IOF e sem feriados (TODO).

### 4.6 Jobs (agendar em produção com token admin)
| Job | Frequência sugerida |
|---|---|
| `POST /admin/tributos/repassar` | diário, início do dia |
| `POST /admin/jobs/rendimento` | diário (dias úteis) |
| `POST /admin/jobs/recorrencias` | diário |
| `POST /admin/jobs/liberar-bloqueios` | a cada hora |
| `POST /admin/jobs/webhooks` | a cada minuto |

---

## 5. App (front) — estado

- Identidade preto/branco + dourado (`--marca` em `app/src/styles.css`).
- **Camada de dados com dois modos** (`src/lib/http.ts` + `src/lib/api.ts`):
  API real quando `VITE_API_URL` existe; mocks (`src/mocks/data.ts`) quando não.
  Os mocks seguem as mesmas regras do backend. O cliente HTTP manda
  `Authorization`, `X-Dispositivo-Id` (id fixo do aparelho no localStorage) e
  `X-Conta`, e renova o token uma vez em 401.
- **Login da pessoa** (`login.tsx`): e-mail + senha. Se o aparelho não é confiável,
  oferece confirmar com verificação facial. Saiu o login "por certificado" e a
  detecção de PJ pelo texto do e-mail (`authPorConta`).
- **Seletor de conta** no topo (`_app.tsx`): pessoal ↔ empresas. Trocar limpa o
  cache do React Query.
- **Cadastro** (`criar-conta.tsx`): pessoa (CPF) e, opcionalmente, empresa (CNPJ,
  porte, regime) no mesmo fluxo. A verificação facial roda no envio (o desafio
  vale 2 minutos).
- **Verificação facial** (`components/payflow/liveness.tsx`): pede o desafio ao
  servidor, guia "de frente → virar para o lado pedido" com MediaPipe e manda os
  quadros sem espelhamento. Corrigido o bug que reiniciava a câmera a cada passo.
- **Transferir**: por chave Pix ou número da conta, sem split, biometria acima de
  R$ 500, tela de "enviado para aprovação" quando passa da alçada.
- **Cobranças (PJ)** (`_app.contas.tsx`): criar cobrança com nota (chave + CBS + IBS),
  parcelamento, Pix copia-e-cola (simulado), lista de cobranças.
- **Início PJ**: card "Imposto das suas vendas" (retido das notas, já repassado,
  repasse de amanhã, projeção 2033), créditos informados + restituição prevista,
  papel e alçada. Saiu o "zero apuração".
- **Configurações**: limites reais e editáveis (carência de 24h no aumento),
  aparelho confiável, papel/alçada, agência/conta, chaves Pix.
- **Só no modo demonstração** (sem endpoint no backend): Loja, Viagens, Cartão
  virtual, contas a pagar. No modo API, Loja/Viagens somem da navegação.
- **Lovable removida**: `vite.config.ts` declara os plugins direto; sem Nitro (o app
  é SPA). O build sai em `dist/client` e `scripts/assemble-www.mjs` já procura lá.
- `src/lib/split.ts`: tabela de transição 2026–2033 igual à do backend; usada só
  para estimativas. `semSplit()` para transferências.
- **Site**: calculadora com os anos da transição e textos corrigidos (sem "zero
  apuração", split só em venda com nota, login por pessoa + alçadas).

## 6. Progresso da correção (2026-10-06)

Ordem de criticidade combinada com o time. ✅ feito · 🟡 parcial · ⬜ falta.

| # | Item | Estado |
|---|---|---|
| 1 | Revogar o token da Expo que vazou no chat | ⬜ **ação manual** (painel da Expo) |
| 2 | Tabela de alíquotas por ano | ✅ backend, app e site |
| 3 | Transferência sem retenção; split só em cobrança | ✅ backend, app e site |
| 4 | Ligar o app ao backend | ✅ (modo API; e2e passou) — falta testar no celular |
| 5 | Limites e aparelho confiável no servidor | ✅ backend + tela de Configurações |
| 6 | Prova de vida no servidor | ✅ — **calibrar em aparelho real** |
| 7 | Cobrança vinculada à NF-e | ✅ backend + tela de Cobranças |
| 8 | Separar conta Governo (admin / caixa / tributos) | ✅ |
| 9 | Créditos como informação | ✅ |
| 10 | Empresa × pessoa × vínculo, alçada | ✅ backend; app tem seletor e alçada, **falta tela de gerir vínculos e aprovar pendentes** |
| 11 | Chaves Pix no lugar do id de 6 dígitos | ✅ |
| 12 | Validar CNPJ (DV + Receita) | ✅ (BrasilAPI; bureau pago é TODO) |
| 13 | Login PJ pela pessoa | ✅ |
| 14 | Rate limit por IP, senha fora do log | ✅ |
| 15 | Regime/setor: imposto lido da nota | ✅ |
| 16 | Trocar "zero apuração" | ✅ app, site e PLANO.md |
| 17 | Dinheiro como string na API | ✅ (app converte só para exibir) |
| 18 | Contestação (MED) e bloqueio cautelar | ✅ backend; **falta botão "contestar" no comprovante** (`api.contestar` já existe) |
| 19 | Estorno, parcelado, MEI/Simples | ✅ backend; estorno sem tela no app |
| 20 | APK, DeepFace fora da request, Lovable, senha no compose | ✅ Lovable, compose, semáforo da biometria; 🟡 APK: CI ajustado, **não verificado** |
| 21 | Pix Automático, lote, webhooks, rendimento | ✅ backend; **sem telas no app** |

### O que ficou para depois (sabido)
- **Telas do app** para: gerir vínculos/alçadas, aprovar operações pendentes,
  contestar transação, estornar cobrança, Pix Automático, lote, webhooks.
  Todos os endpoints existem (ver `/docs`).
- **Postgres**: a migração v7 não foi rodada num Postgres real.
- **Biometria real**: o caminho DeepFace (sem `BIOMETRIA_STUB`) não foi exercitado
  com câmera; o sinal/limiar do giro precisa de calibração.
- **Pix/boleto de verdade**: copia-e-cola e linha digitável são simulados (exige SPI/DICT ou parceiro).
- Confirmação por código de chave Pix e-mail/celular; IR/IOF e feriados no rendimento;
  emissão real de cartão; contas a pagar (DDA).
- Tokens no `sessionStorage` (aceitável para web; no apk, migrar para armazenamento seguro do Capacitor).

## 7. O .apk — estado

App é **Capacitor (web)**, não Expo — o token da Expo não serve. Build na nuvem
via `.github/workflows/android.yml` (artefato `PayFlow-debug-apk`).

Mudanças de 2026-10-06 (não verificadas, porque o CI roda no GitHub):
- **JDK 17 → 21** e **Node 20 → 22** no workflow: Capacitor 7+ e AGP 8.13 exigem JDK 21.
- `app/android/gradle.properties`: `-Xmx1536m` → `-Xmx4g`.
- O build web agora sai em `app/dist/client` (sem Nitro/Lovable);
  `scripts/assemble-www.mjs` procura lá e monta `www/` normalmente (testado local).

Se ainda falhar, ler a annotation `GRADLE_FAIL` da execução no GitHub Actions.

## 8. Segurança

- O token da Expo colado no chat está **comprometido**: revogar no painel da Expo.
- Não commitar segredos. `.env` está no `.gitignore`.

## 9. Próximos passos

Ver a tabela da seção 6 (itens ⬜).
