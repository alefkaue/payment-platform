# PayFlow — Handoff (para continuar o trabalho)

Documento de passagem de bastão. Resume o que já foi feito, como rodar, as decisões
tomadas e **o que falta** — para outra IA/dev continuar de onde paramos.
Complementa o `PLANO.md` (plano de produto). Data: 2026-10-06.

---

## 1. O que é o projeto

**PayFlow** — banco digital brasileiro cujo diferencial é o **split de IBS/CBS da
Reforma Tributária** resolvido no ato do pagamento. Foco de venda: **empresas**
(split + créditos tributários), mas também atende **PF**. Vai ser apresentado para
Mercedes e Scania.

## 2. Estrutura do repositório (monorepo)

```
app/        # App (web Vite + TanStack Router, em TypeScript) + empacotamento mobile Capacitor (android/)
site/       # Vitrine institucional (Next.js 15 + React 19, TypeScript)
backend/    # API FastAPI v6 (JWT, split, biometria, Postgres/SQLite) — ainda NÃO ligada ao app
.github/workflows/android.yml  # CI que gera o .apk na nuvem
PLANO.md    # plano de produto (pesquisado)
HANDOFF.md  # este arquivo
```

GitHub: `https://github.com/alefkaue/payment-platform` (público). Branch `main` já
tem o monorepo organizado; existe também o branch `monorepo-organizado`.

> **Sobras fora do repo (só no disco local, já ignoradas no .gitignore):**
> `_legacy_backend/`, `_legacy_frontend/`, `_extract_pixel/`, `payment/` (continha o
> app Expo antigo), `*.zip`, `inicio.jpeg`. Podem ser apagadas — não são usadas.

## 3. Como rodar

- **App (web):** `cd app && npm install && npm run dev` → http://localhost:8081 (ou 8080).
  - Login é demo: qualquer e-mail/senha. E-mail com "empresa"/"pj"/"ltda" → conta **PJ**; senão **PF**.
- **Site:** `cd site && npm install && npx next dev -p 8090`.
- **Backend:** `cd backend` (FastAPI; ver `backend/README`/docker-compose). Roda local nos testes.
- **Type-check:** `npx tsc --noEmit` em `app/` e em `site/` (ambos passam). Testes: `cd app && npm test`.

### Gotchas de ambiente (importante)
- `app/` usa **strict tsc** (`exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`, `noPropertyAccessFromIndexSignature`). Cuidar de acessos indexados e optional props.
- `app/` é **SSR (TanStack Start/Nitro)** com **modo SPA ligado** (`vite.config.ts` → `tanstackStart.spa.enabled`). O build gera `.output/public/_shell.html` (shell SPA estático).
- `site/` teve que ir para **Next 15 / React 19** (Next 14 quebrava no Node 24 na verificação de TS) e **TypeScript fixado em 5.x** (TS 7 não é suportado).
- Este PC não tem Java/Android SDK; `py` existe (Python 3.14). API do GitHub sem login tem **rate limit de 60/h** (cuidado ao pollar).

## 4. O que já foi construído (app)

- **Identidade:** preto & branco + **dourado** (gold `#d4af37`; token `--marca` em `app/src/styles.css`). A "moeda" da logo é dourada.
- **Onboarding** (`routes/bem-vindo.tsx`): tela fixa estilo stories (foto full-bleed, barra de progresso), **dois botões "Criar conta" / "Entrar"**, ícone de ajuda. Fotos em `app/public/welcome/` (Unsplash; a de "empresa" é paisagem genérica — **trocar**).
- **Login** (`routes/login.tsx`): conta + senha + **método adaptativo** (biometria para PF/MEI; **certificado e-CNPJ** para PME/Grande — ver `src/lib/empresa.ts`).
- **Verificação facial com liveness** (`components/payflow/liveness.tsx`, MediaPipe FaceLandmarker via CDN): piscar + virar o rosto. Ligada no login e no cadastro; substituiu a foto/selfie. Permissão `CAMERA` no AndroidManifest. **Não testada com câmera real** — afinar thresholds de yaw/blink no device.
- **Home PF** estilo PicPay: saldo + **"Rende 100% do CDI"** (teaser) + carrossel de banners + "Pro dia a dia". Split invisível para PF.
- **Painel PJ** (indústria): apuração automática (crédito abate imposto), **regime por setor**, créditos IBS/CBS, caixa preservado, contas a pagar/receber (NF-e), acesso & assinaturas (e-CNPJ, alçadas/dupla autorização).
- **Configurações** (`routes/_app.config.tsx`): **cartão virtual** (congelar, travas online/internacional, **CVV dinâmico**, limite), limites (PF×PJ), segurança, dados, **"Sair" (fica aqui dentro, não no header)**.
- **Split por setor/regime** (`src/lib/split.ts`): padrão/−30%/−60%/zero (`REGIMES`, `aliquotaRegime`, `regimeDoSetor`). Também no simulador do site.
- **Header** com avatar/iniciais (antes o nome ficava "solto").
- **Camada de dados** mockada em `src/lib/api.ts` → `src/mocks/data.ts` (telas nunca importam mocks direto). `src/lib/split.ts` é a fonte única do cálculo.
- **Removido:** animação de splash (o usuário não gostou; se refizer, ele quer só a **moeda girando no próprio eixo**, sem a coreografia do nome).

## 5. Backend (FastAPI v6) e o DB

- Em `backend/`. Já tem JWT, split (`services/split_service.py`, alíquotas iguais às do front), biometria (DeepFace), auditoria, etc.
- **Schema atualizado para casar com o front** (migration `alembic/versions/b2c7f1a9d3e4_cartoes_porte_creditos_regime.py`):
  - tabela **`cartoes`**, `usuarios.porte` (MEI/PME/GRANDE), `usuarios.regime_tributario`, `carteiras.creditos`.
- **AINDA NÃO está ligado ao app** (o app usa mocks). Próximo passo grande: expor endpoints (porte, créditos, apuração, faturas, cartão, auth por certificado) e trocar o corpo das funções de `app/src/lib/api.ts` por `fetch`.

## 6. O .apk — estado atual (ponto onde paramos) ⚠️

**Decisão técnica importante:** o app é **Capacitor (web)**, não Expo/React Native.
Por isso **o token da Expo/EAS NÃO serve** para buildar este app (EAS é para
Expo/RN; exige `app.json`/projeto Expo). O APK antigo que o usuário gerou antes era
o app **Expo** legado (outro código, design antigo).

**Caminho adotado (correto para Capacitor):** build na nuvem via **GitHub Actions**
(`.github/workflows/android.yml`) → publica `app-debug.apk` como **artefato** da
execução (aba Actions → run → Artifacts). Mesmo fluxo "o CI builda, você baixa".

**Progresso do CI (iterado):**
1. ✅ `setup-android` corrigido (fixar `cmdline-tools-version: 11076708` + `packages`).
2. ✅ `vite build` e montagem do `www` passam.
3. ✅ `npx cap sync/copy` falhava no runner → **substituído por cópia via shell** do `www` para `android/app/src/main/assets/public` + escrever `capacitor.config.json` (sem Capacitor CLI no CI).
4. ❌ **BLOQUEIO ATUAL:** o passo **`./gradlew assembleDebug` falha**. A causa exata
   ainda não foi capturada (a última execução adicionou um `::error::` com o tail do
   log do Gradle para virar **annotation** legível pela API; não deu para ler ainda
   por **rate limit** da API do GitHub).

**Como continuar o APK (próxima IA/dev):**
- Ler o erro do Gradle: na run mais recente em `main`, ver a **annotation** (`GRADLE_FAIL ...`) ou o **log do passo "Gerar APK de debug"** (precisa estar logado no GitHub; via API: `GET /repos/alefkaue/payment-platform/actions/runs/{id}/jobs` e os logs do job).
- Suspeitas prováveis (Gradle 8.14.3 + **AGP 8.13.0** + **compileSdk 36**):
  1. **JDK**: subir de 17 → **21** no workflow (`setup-java` java-version 21) — AGP/SDK 36 novos.
  2. **Memória**: `app/android/gradle.properties` está com `-Xmx1536m`; subir para `-Xmx4g`.
  3. Faltar componente de SDK/build-tools 36 (confirmar que `build-tools;36.0.0` instala).
- Depois do APK gerado: baixar o artefato `PayFlow-debug-apk`, instalar no Android
  (ativar "fontes desconhecidas"). Backend roda local para os testes.
- Alternativa local: `cd app && npm run build:mobile && cd android && ./gradlew assembleDebug` (precisa Android Studio/JDK).

## 7. GitHub — estado e pendências

- `main` foi atualizada com **push normal** via `git merge -s ours origin/main` (mantém a árvore organizada; a v6 antiga fica como ancestral no histórico). **Não** foi usado `--force`.
- **`git push --force` está BLOQUEADO** pela trava de segurança do Claude Code (ação destrutiva). Se precisar sobrescrever histórico, o usuário roda `!git push --force ...` ou libera a permissão.
- Credenciais do GitHub já estão em cache no PC (push normal funciona). **Não** é preciso procurar key.

## 8. Segurança

- O usuário **colou um token da Expo no chat** — está **comprometido**; deve ser **revogado/rotacionado**. Não foi usado (não se aplica ao Capacitor) e não está em lugar nenhum do repo.
- Não commitar segredos. `.env` está no `.gitignore`.

## 9. Próximos passos sugeridos (prioridade)

1. **Fechar o APK** (corrigir o `assembleDebug` — ver §6).
2. **Ligar o backend ao app** (trocar mocks por `fetch`; §5).
3. **Rendimento/caixinhas e cashback** de verdade (chamariz PF — ver PLANO.md).
4. Fluxo **"cobrar cliente" (PJ)** mostrando o split inteligente ao vivo.
5. Trocar a foto genérica da empresa no onboarding.
6. Remover a conexão **Lovable** (trocar `@lovable.dev/vite-tanstack-config` pelo plugin padrão do TanStack Start — deps já presentes; remover `app/.lovable/` e notas do `app/AGENTS.md`). Fazer por último.
7. Apagar as sobras do disco (§2).
