# Astro — plano de segurança e pentest

> Documento vivo. Criado em 09/10/2026 (3ª sessão do Claude Code), a pedido do Alef:
> **foco em segurança (back e front), não em design**, preparando o projeto para subir no **Azure** e
> passar por **pentest de outros grupos**. A seção 5 é o diário: o que já foi feito, em que commit, e
> por onde continuar. Complementa o `HANDOFF-V9.md` (estado geral do projeto).

---

## 1. Pesquisa (resumo do que guia as decisões)

| Tema | O que a referência diz | Fonte |
|---|---|---|
| Autenticação de API | OWASP API2:2023: tokens curtos, rotação de refresh, **tokens com remetente amarrado (DPoP / mTLS)**, rate limit e bloqueio contra força bruta, encerrar sessão em todos os aparelhos. | [apisecurity.io API2:2023](https://apisecurity.io/owasp-api-security-top-10/api2-2023-broken-authentication/), [Wiz](https://www.wiz.io/api/md/academy/api-security/broken-api-authentication) |
| Burlar a biometria | Dois ataques: **apresentação** (foto/vídeo/máscara na frente da câmera — ISO 30107-3) e **injeção** (câmera virtual tipo OBS ou chamada direta à API com quadros sintéticos). A ISO 30107 não cobre injeção; defesa em camadas é muito melhor que uma camada só; **atestação do aparelho** prova que o quadro veio de um sensor real. | [Signzy](https://www.signzy.com/blogs/liveness-detection-deepfake-injection-attacks), [Joinble](https://joinble.io/en/blog/injection-attacks-liveness-detection-kyc), [FaceTec/ENISA](https://facetec.com/ENISA_RFI_Remote_ID_Attacks_FaceTec_Countermeasures.pdf) |
| Atestação de app | Play Integrity (Android) e App Attest (iOS), sempre **verificados no servidor** com nonce emitido pelo servidor. | [OWASP MASWE-0054](https://mas.owasp.org/MASWE/MASVS-RESILIENCE/MASWE-0054/), [Expo app-integrity](https://docs.expo.dev/versions/v55.0.0/sdk/app-integrity/) |
| App móvel | MASVS-STORAGE: token no **Keychain/Keystore**, nunca em armazenamento comum, log ou backup; **certificate pinning**. | [Capgo token storage](https://capgo.app/blog/secure-token-storage-best-practices-for-mobile-developers/), [OWASP MASVS](https://appsecsanta.com/mobile-security/owasp-masvs-guide) |
| Pentest no Azure | Não precisa de autorização prévia da Microsoft, mas vale as **Rules of Engagement**: só recursos próprios; **proibido DoS/DDoS** e atacar outros tenants. | [Microsoft Learn — pen testing](https://learn.microsoft.com/en-my/azUre/security/fundamentals/pen-testing), [Wiz](https://wiz.io/academy/vulnerability-management/azure-penetration-testing) |
| WAF no Azure | Front Door **Standard** só tem regras próprias (inclusive rate limit); regras gerenciadas OWASP e bot protection só no **Premium** (caro para conta de estudante). | [Microsoft Learn — WAF no Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/waf-overview) |
| Conta de estudante | Azure for Students: US$ 100 de crédito + serviços gratuitos por 12 meses, sem cartão. | [Azure for Students](https://azure.microsoft.com/en-us/free/students) |
| Distribuir app para teste | Android: APK direto (sideload). iOS: **precisa de conta Apple Developer** (TestFlight ou Ad Hoc com UDID) e de um Mac para compilar. | [Capawesome](https://capawesome.io/blog/how-to-distribute-ios-and-android-apps-to-testers/), [TestApp.io](https://blog.testapp.io/how-to-distribute-your-ios-app-without-using-the-app-store/) |

## 2. Achados no código (análise de 09/10/2026)

Gravidade: 🔴 crítico · 🟠 alto · 🟡 médio · ⚪ baixo.

| # | Gravidade | Achado | Onde |
|---|---|---|---|
| A1 | 🔴 | **Desafio de prova de vida é sempre igual** (login = piscar 3x; cadastro = mesma sequência fixa). Quem gravar uma vez os quadros de alguém (vídeo, malware, ombro) reenvia com qualquer desafio novo e passa: o desafio só tem id, não muda o que se pede. É o "burlar biometria" mais fácil. | `services/liveness_logic.py` (`PASSOS` fixos) |
| A2 | 🟠 | **Roubo de token**: access e refresh ficam no `sessionStorage` e o id do aparelho no `localStorage`. A "amarração ao aparelho" é só o valor de um header escolhido pelo cliente: quem rouba o token (XSS, extensão, malware) rouba o id junto e usa de outro lugar. | `app/src/lib/http.ts`, `deps.py` (`hash_dispositivo`) |
| A3 | 🟠 | Sessão sem **tempo máximo absoluto** nem **expiração por inatividade**: o refresh renova por 7 dias indefinidamente. Banco costuma derrubar em minutos parado. | `auth_service.renovar`, `REFRESH_TOKEN_EXP_DIAS` |
| A4 | 🟠 | Força bruta: limite por e-mail (10/15 min) e por IP (30/15 min) existe, mas **cadastro, refresh e consulta de convites não têm limite**; não há atraso progressivo nem aviso ao dono da conta; `POST /usuarios` responde "e-mail já existe"/"CPF já existe" (enumeração de contas). | `routers/contas.py`, `contas_service.criar_pessoa` |
| A5 | 🟡 | Front sem **CSP** e cabeçalhos de segurança no host estático; **overlay de debug da câmera ligado**; build sem `VITE_API_URL` vira modo demonstração (qualquer login entra) — um deploy errado expõe isso. | `liveness.tsx` (`DEBUG_OVERLAY`), `http.ts` |
| A6 | 🟡 | Deploy de demonstração **deriva os segredos do `DATABASE_URL`** (quem descobre a URL do banco forja tokens) e libera CORS para **qualquer** `*.netlify.app`. | `backend/entrypoint-demo.sh`, `Dockerfile` (raiz) |
| A7 | 🟡 | Injeção de câmera virtual na web não tem como ser 100% barrada; no app nativo dá para exigir **Play Integrity / App Attest**. Hoje não há nenhum dos dois. | — |
| A8 | ⚪ | Superfície de ataque extra: Loja, Viagens e pontos (endpoints e telas) sem uso no foco atual. | `routers/beneficios.py`, rotas `_app.loja*`, `_app.viagens*` |

Pontos que **já estão bons** (manter): Argon2id; JWT com `iss/aud/nbf/typ` e algoritmo fixo; rotação de
refresh com detecção de reuso (revoga a família); desafio de uso único com validade e dono; anti-spoof e
"mesma pessoa no início, meio e fim"; limites de valor no servidor; problem+json sem stack; cabeçalhos de
segurança na API; `BIOMETRIA_STUB`/`DEPOSITO_DEMO`/stubs **proibidos em produção** (o app não sobe).

## 3. Lista de trabalho (em ordem de importância)

| # | Item | Resolve | Estado |
|---|---|---|---|
| 1 | **Desafio aleatório** de prova de vida (ordem e ações sorteadas pelo servidor; quadros fora da ordem pedida não passam) | A1 | ✅ |
| 2 | **Prova de posse da chave (DPoP-like)**: o app gera um par de chaves **não exportável** (WebCrypto; no APK, Keystore/Keychain), registra a pública no login e **assina cada requisição** (método, caminho, horário, nonce). Token roubado sem a chave não serve. Tokens saem do `sessionStorage` (memória + refresh amarrado à chave). | A2 | ⬜ |
| 3 | **Sessão**: máximo absoluto (ex.: 12 h) e inatividade (ex.: 15 min) no servidor; aviso de login em aparelho novo | A3 | ⬜ |
| 4 | **Força bruta e enumeração**: rate limit em cadastro/refresh/convites; atraso progressivo; tentativas por `mfa_token`; resposta neutra no cadastro | A4 | ⬜ |
| 5 | **Cadastro em etapas** (dados → documento → rosto, cada um numa página) e **documento frente e verso obrigatórios** (no app e no backend) | pedido do Alef | ⬜ |
| 6 | **Arquivar Loja/Viagens/pontos**: telas para `app/src/_arquivado/`, fora da navegação; backend com `BENEFICIOS_HABILITADOS=0` por padrão | pedido do Alef, A8 | ⬜ |
| 7 | **Front**: CSP e cabeçalhos no host (Static Web Apps), overlay de debug só em dev, build de produção recusa modo demonstração | A5 | ⬜ |
| 8 | **Segredos e config**: tirar a derivação de segredos e o CORS `*.netlify.app`; Key Vault no Azure | A6 | ⬜ |
| 9 | **Azure + WAF + `PENTEST.md`** (escopo, regras, contas de teste, como reportar) e APK Android pelo CI | objetivo do pentest | ⬜ |
| 10 | **App nativo**: tokens no Keystore/Keychain, certificate pinning, Play Integrity / App Attest | A7 | ⬜ (depois do APK existir) |

## 4. Como os outros grupos vão fazer o pentest (proposta)

**Ambiente.** Um ambiente **só para o pentest** no Azure (não o da apresentação), com dados falsos:
- API: Azure Container Apps (escala a zero, cabe no crédito de estudante) + Postgres Flexible (B1ms) +
  Key Vault para os segredos. HTTPS automático.
- Front (PWA): Azure Static Web Apps (grátis), com CSP e cabeçalhos.
- WAF: Front Door Standard com **regras de rate limit** (o Premium, com regras OWASP gerenciadas, custa caro).
  Para o pentest dá para ligar o WAF em modo **detecção** primeiro, para os grupos testarem o app de verdade e
  não só o WAF — e depois em **prevenção**, para uma segunda rodada.
- Logs no Log Analytics: cada achado dos grupos pode ser conferido nos logs (e vira material da apresentação).

**Regras (vão no `PENTEST.md`, item 9).** Escopo = só as URLs do ambiente de pentest e o APK; **proibido
DoS/DDoS** (regra da Microsoft) e atacar outros recursos do Azure ou de outros tenants; contas de teste
entregues pela equipe (PF, MEI, PME e Grande com papéis diferentes); janela de datas combinada; achados
reportados num modelo (passos, impacto, evidência). A biometria fica **ligada de verdade** — o objetivo é
justamente ver se alguém burla.

**Celular.**
- **Android**: APK gerado pelo GitHub Actions (já existe o workflow) apontando para a API do Azure. Os grupos
  instalam direto (sideload). É o que dá para fazer sem custo.
- **iPhone**: um app nativo exige **conta Apple Developer (US$ 99/ano) e um Mac** para compilar e distribuir
  (TestFlight). Sem isso, a saída é o **PWA**: no iPhone, abrir o site no Safari → "Adicionar à Tela de
  Início". Câmera e prova de vida funcionam no Safari. Recomendação: Android = APK; iPhone = PWA, a menos que
  alguém do grupo tenha Mac e conta Apple.

## 5. Diário (o que foi feito)

- 09/10 — Pesquisa, análise e esta lista. Nada implementado ainda.
- 09/10 — **Item 1 feito.** `liveness_logic.py` reescrito: o servidor sorteia os passos (`secrets.SystemRandom`;
  login = 2 ações entre piscar 2x/3x, sorrir, virar esq./dir.; cadastro = as 4, embaralhadas) e grava
  `"modo:passos"` na coluna `acao` (migração `a1b2c3d4e5f6`, 20 → 80 caracteres). A conferência exige os
  passos **na ordem** (janelas consecutivas da série) e **reprova ação não pedida** (virar para lado não
  pedido, sorrir sem pedido, piscar além de 1 extra) — gravação antiga ou vídeo "que faz tudo" não passam.
  Desafios antigos (só o modo) continuam aceitos até expirarem. App: `liveness.tsx` entende `piscar2` e
  qualquer ordem; o **overlay de debug só aparece no `npm run dev`**. Testes: `test_liveness.py` com replay,
  vídeo universal, fora de ordem e ação extra (155 testes no backend).
  **Calibrar num aparelho real**: a tolerância de piscadas naturais (`PISCADAS_EXTRAS`, `PISCADAS_NATURAIS_MAX`).
