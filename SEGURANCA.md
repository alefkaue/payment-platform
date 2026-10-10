# Astro — plano de segurança e pentest

> Documento vivo. Criado em 09/10/2026 (3ª sessão do Claude Code), a pedido do Alef:
> **foco em segurança (back e front), não em design**, preparando o projeto para subir no **Azure** e
> passar por **pentest de outros grupos**. A seção 5 é o diário: o que já foi feito, em que commit, e
> por onde continuar. Complementa o `HANDOFF-V9.md` (estado geral do projeto).
>
> **PARA A PRÓXIMA SESSÃO (parou em 10/10, 4ª sessão):** itens 1 a 8 feitos. Continue no
> **item 9** da tabela da seção 3 e siga a ordem. Antes de mexer: `git pull`. Rode os testes do backend
> (`cd backend && .venv/Scripts/python.exe -m pytest`, 188 passando) e do app (`cd app && npx tsc --noEmit &&
> npx vitest run`). Atenção: o PC do Alef fica sem memória com app + backend + câmera abertos ao mesmo tempo.

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
| 2 | **Prova de posse da chave (DPoP, RFC 9449)**: o app gera um par de chaves **não exportável** (WebCrypto; no APK, Keystore/Keychain), o login amarra os tokens à impressão da chave e **cada requisição vai assinada** (método, caminho, horário, id único, hash do token). Token roubado sem a chave não serve. | A2 | ✅ (falta Keystore no app nativo, item 10) |
| 3 | **Sessão**: máximo absoluto (ex.: 12 h) e inatividade (ex.: 15 min) no servidor; aviso de login em aparelho novo | A3 | ✅ (aviso por e-mail/push: depois) |
| 4 | **Força bruta e enumeração**: rate limit em cadastro/refresh/convites; atraso progressivo; tentativas por `mfa_token`; resposta neutra no cadastro | A4 | ✅ |
| 5 | **Cadastro em etapas** (dados → documento → rosto, cada um numa página) e **documento frente e verso obrigatórios** (no app e no backend) | pedido do Alef | ✅ |
| 6 | **Arquivar Loja/Viagens/pontos**: telas para `app/src/_arquivado/`, fora da navegação; backend com `BENEFICIOS_HABILITADOS=0` por padrão | pedido do Alef, A8 | ✅ |
| 7 | **Front**: CSP e cabeçalhos no host (Static Web Apps), overlay de debug só em dev, build de produção recusa modo demonstração | A5 | ✅ |
| 8 | **Segredos e config**: tirar a derivação de segredos e o CORS `*.netlify.app`; Key Vault no Azure | A6 | ✅ (Key Vault entra com a infra, item 9) |
| 9 | **Azure + WAF + `PENTEST.md`** (escopo, regras, contas de teste, como reportar) e APK Android pelo CI | objetivo do pentest | 🟡 escrito, falta subir (precisa da conta Azure) |
| 10 | **App nativo**: chave DPoP no Keystore com **atestação de hardware** conferida no servidor (no lugar do Play Integrity), certificate pinning, sem backup/print/depuração, APK release assinado | A7 | 🟡 escrito e testado no backend; falta compilar no CI e testar num celular |

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
- 09/10 — **Item 2 feito (DPoP, RFC 9449).** Backend: `app/core/dpop.py` valida a prova (ES256, `jwk` pública no
  cabeçalho, sem chave privada, `htm`/`htu`/`iat` ±60 s, `ath` = hash do access token, `jti` de uso único na
  tabela `dpop_jtis` — migração `b7c8d9e0f1a2`). O `jkt` (impressão da chave) entra no mfa_token, no access e no
  refresh (`cnf.jkt`); `deps.usuario_atual` exige prova da MESMA chave em toda requisição; refresh só renova com
  a mesma chave. `DPOP_OBRIGATORIO=1` por padrão e **proibido desligar em produção**. CORS libera o header `DPoP`.
  App: `src/lib/dpop.ts` (par ECDSA P-256 **não exportável** no IndexedDB; prova em cada requisição e no
  refresh). Corrigido junto: refreshes em paralelo (ex.: tela de Aprovações faz 3 GETs) eram vistos como
  **reuso de refresh** e derrubavam a sessão — agora uma renovação por vez. Testes: `test_dpop.py` (10 ataques:
  token sem chave, chave do atacante, prova reenviada, outro método/endereço/horário, `ath` errado, `alg none`,
  chave privada no cabeçalho, refresh roubado, etapa do rosto com outra chave, produção sem DPoP). 165 testes;
  e2e do app passou com DPoP obrigatório.
  **Decisão**: os tokens continuam no `sessionStorage` (sair dele obrigaria refazer login com rosto a cada
  recarregar a página). Com DPoP, copiar o token não basta: XSS ainda poderia usar a chave **enquanto a aba está
  aberta** — por isso o item 7 (CSP) continua importante.
  **Para o pentest**: quem for testar a API direto precisa gerar provas DPoP (ver `tests/test_dpop.py`, classe
  `Chave`, ou qualquer biblioteca DPoP); isso vai no `PENTEST.md`.
- 09/10 — **Item 3 feito.** Refresh e access carregam `auth_time` (hora do login com senha + rosto), que
  atravessa as renovações. `auth_service.renovar` recusa: sessão com mais de `SESSAO_MAX_HORAS` (12 h) desde o
  login e refresh sem uso há mais de `SESSAO_INATIVIDADE_MIN` (30 min; como o access vive 15 min, a queda real
  por inatividade fica entre 15 e 30 min). Relógio real (o mesmo do JWT), isolado em `_relogio()` para teste.
  Login em aparelho novo grava `login_aparelho_novo` na trilha (`GET /seguranca/atividade`). Testes:
  `test_sessao.py`. 169 testes.
  **Falta no app**: quando o refresh falha (401), mandar para a tela de login com o motivo, em vez de só
  mostrar erro na tela atual.
- 09/10 — **Item 4 feito.** `app/core/limites.py` (`limitar_por_ip`, eventos no banco — vale com várias instâncias;
  429 com `Retry-After`): cadastro `CADASTRO_MAX_IP_HORA` (10/h) e refresh `REFRESH_MAX_IP_15MIN` (120/15 min).
  O bloqueio de login por conta (10 erros/15 min, independe do IP — segura senha distribuída por vários IPs)
  agora grava `login_bloqueado_tentativas` na trilha da pessoa. Cadastro com e-mail **ou** CPF já usado responde
  a mesma mensagem (não revela qual dado existe). Login de conta inexistente e senha errada já respondiam igual
  (com hash falso para igualar o tempo). Testes: `test_forca_bruta.py`. 174 testes.
  **Atenção**: numa rodada da suíte 1 teste falhou e não se repetiu em 5 rodadas seguidas. Se voltar a acontecer,
  rodar `pytest -rf` para ver qual é (suspeitos: testes que usam o relógio real em `test_sessao.py`).
- 09/10 — **Item 5 feito.** `criar-conta.tsx` virou um passo a passo com uma tela por etapa e barra de progresso:
  **dados** (com "repita a senha") → **documento** (frente **e verso obrigatórios** para RG/CNH/CIN; passaporte
  só a página da foto; na PJ, o documento da empresa) → **rosto** (ao concluir a prova de vida a conta é criada
  na hora, porque o desafio vence em 2 min) → **entrar** (rosto do 1º login e, na PJ, abertura da empresa).
  Se o servidor recusar, a tela volta para a etapa que resolve (dados ou documento). Backend:
  `documento_service` recusa RG/CNH/CIN sem verso (`TIPOS_COM_VERSO`) — vale também para quem chama a API direto.
  Teste `test_documento_exige_frente_e_verso`. 175 testes. **Não testado visualmente no navegador** (o PC estava
  sem memória para subir app + câmera); conferir as 4 telas no celular.
- 09/10 — **Item 6 feito.** App: telas `_app.loja.tsx`, `_app.loja.$id.tsx`, `_app.viagens.tsx` e os cartões
  `ProdutoCard`/`VooCard` movidos para `app/src/_arquivado/beneficios/` (fora de `src/routes`, do `tsc` e do
  `eslint`; o `README.md` de lá explica como reativar). Saíram os atalhos (barra PF agora tem Extrato no lugar
  de Loja; banners, atalhos e "pontos" da home; botão de pontos em Cartões; notificação de pontos do modo demo)
  e a leitura de `/pontos` em `minhaConta()`. Backend: `BENEFICIOS_HABILITADOS=0` por padrão — rotas de
  Loja/Viagens/pontos respondem 404 e o catálogo não é criado no boot (os testes ligam o módulo; teste novo
  `test_beneficios_desligados_respondem_404`). 176 testes no backend; app `tsc`/`vitest` ok.
- 09/10 (4ª sessão) — **Item 7 feito.**
  (a) **Sessão que cai volta para o login com o motivo.** O backend já mandava `WWW-Authenticate` em todo 401
  de sessão (`deps.py`, DPoP) e **não** manda nos 401 de biometria ("rosto não confere"); agora o CORS expõe
  esse header (`main.py`, `expose_headers`) e o app usa isso para separar os dois casos. `http.ts`: 401 de
  sessão → tenta o refresh uma vez; se o servidor recusa (tempo máximo, inatividade, sessão encerrada, outro
  aparelho), limpa tokens/conta, guarda o motivo do servidor e avisa `aoExpirarSessao`; o `AuthProvider`
  zera o estado e o cache do React Query e o layout manda para `/login`, que mostra o motivo
  (`motivoSaida`, lido uma vez). Refresh com 429/5xx ou sem rede **não** desloga (erro passageiro). 401 de
  biometria não renova nem derruba (antes gastava um refresh e reenviava o desafio já usado). 401 nas rotas
  `/auth/login*`, `/auth/refresh`, `/auth/logout` não é "queda de sessão"; `/auth/eu` e `/auth/sessoes`
  agora também renovam.
  (b) **Build de produção recusa o modo demonstração**: `vite.config.ts` falha no `vite build` (modo
  production) sem `VITE_API_URL`, a não ser com `VITE_MODO_DEMO=1` explícito. O CI do APK lê a URL da
  variável do repositório `ASTRO_API_URL` e, sem ela, gera de propósito o APK de demonstração.
  **Atenção no deploy da apresentação (Netlify)**: o build agora exige `VITE_API_URL` (ou `VITE_MODO_DEMO=1`).
  (c) **CSP e cabeçalhos no host**: `scripts/cabecalhos.mjs` roda depois do `vite build` (`npm run build`) e
  grava em `dist/client` o `staticwebapp.config.json` (Azure Static Web Apps: CSP, fallback do SPA, cache) e o
  `_headers` + `_redirects` (Netlify). CSP **sem `'unsafe-inline'` em script**: os 3 scripts inline do shell
  do TanStack entram por **hash SHA-256** calculado do `_shell.html` gerado (o hash segue o parser HTML: o
  estado do roteador tem um caractere NUL que o navegador troca por U+FFFD — sem isso a página ficava em
  branco). Liberado só: MediaPipe (`cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/` e
  `storage.googleapis.com/mediapipe-models/`), Google Fonts, a API (`VITE_API_URL`) e o sync do modo demo;
  `'wasm-unsafe-eval'` (WebAssembly do MediaPipe, não libera `eval`); `frame-ancestors 'none'`,
  `object-src 'none'`, `base-uri 'none'`. Mais: `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy:
  no-referrer`, `Permissions-Policy: camera=(self)` e o resto desligado, COOP, HSTS. Estilo inline continua
  liberado (bibliotecas de UI injetam `<style>`). `assemble-www.mjs` troca `/_shell.html` por `/index.html`
  nesses arquivos quando monta o `www/`.
  **Testado no Chrome** com um servidor que aplica o `_headers`: login renderiza, a prova de vida abre a câmera
  e o MediaPipe rastreia o rosto sem nenhuma violação; script inline injetado e `fetch` para outro domínio
  são bloqueados. Testes: `app/src/lib/sessao.test.ts` (5 casos) e `cabecalhos.test.ts` (6 casos);
  backend `test_sessao_recusada_tem_www_authenticate_visivel_para_o_app`. 177 testes no backend; app 17.
  **Ressalva**: a CSP vale no host web (PWA). No APK (Capacitor) quem serve é o WebView, sem esses headers —
  fica para o item 10.
- 10/10 (4ª sessão) — **Item 8 feito.** `backend/entrypoint-demo.sh` **não deriva mais segredo nenhum** do
  `DATABASE_URL`: sem `JWT_SECRET` (32+), `EMBEDDING_KEY` (Fernet válida), `ADMIN_SENHA` e `CORS_ORIGINS` ele
  nem sobe e diz como gerar cada um. `Dockerfile` da raiz sem o `CORS_ORIGIN_REGEX` de `*.netlify.app` (qualquer
  site no Netlify podia chamar a API como se fosse o app); a origem agora é a URL exata. `render.yaml`: o Render
  **gera** `JWT_SECRET` e `ADMIN_SENHA` e **pede** `EMBEDDING_KEY` e `CORS_ORIGINS` na criação.
  `config.get_settings` em produção confere **no boot** (não só no primeiro uso): `JWT_SECRET` 32+,
  `EMBEDDING_KEY` Fernet válida, `ADMIN_SENHA` 16+, CORS só com origens `https://` exatas (sem `*`, sem regex).
  `.env.example` da raiz cobre **todas** as variáveis do `config.py` (conferido por script), agrupadas, com o que
  é proibido em produção. Testes: `tests/test_config_producao.py` (11 casos); entrypoint testado à mão (falta
  variável / JWT curto / Fernet inválida → sai com erro). 188 testes no backend.
  **Atenção — deploy de demonstração já existente no Render**: depois deste commit ele **não sobe** até ganhar
  as 4 variáveis no painel. Como a `EMBEDDING_KEY` muda, as biometrias cadastradas lá deixam de abrir (cada
  pessoa refaz o cadastro, ou recria-se o banco) e as sessões abertas caem (JWT novo).
- 10/10 (5ª sessão) — **Item 9 escrito, não implantado** (não há conta Azure nem Docker nesta máquina).
  `infra/azure/main.bicep` (compila e passa no lint do Bicep 0.48): VNet com Postgres Flexible B1ms **só
  privado**, Key Vault RBAC com os 4 segredos, identidade gerenciada (AcrPull + Secrets User), ACR, Container
  Apps (probes em `/saude`, 1–3 réplicas), Static Web Apps (CSP do `cabecalhos.mjs`) e Front Door Standard
  com WAF (30 req/min por IP em `/auth|/biometria|/identidade`, 300 req/min no geral). Deploy em 2 passos
  (sem imagem → `az acr build` → com imagem), roteiro em `AZURE.md`. `.github/workflows/azure.yml`: login
  **OIDC** (sem segredo no GitHub), `az acr build` com o SHA + nova revisão; front com o token do SWA lido na
  hora. `backend/Dockerfile` endurecido: Tesseract + por, modelos baixados e conferidos no build e só leitura,
  `MODELOS_DOWNLOAD=0`, `AMBIENTE=producao`, uvicorn `--no-server-header --no-proxy-headers`;
  `backend/.dockerignore`. **IP do cliente**: `PROXIES_CONFIAVEIS` aceita CIDR (o proxy do Container Apps muda
  de IP) e `FRONT_DOOR_ID` faz a API usar `X-Azure-ClientIP` só quando `X-Azure-FDID` bate (2 testes; 189 no
  backend). CORS inclui `https://localhost` (origem do APK Capacitor). `PENTEST.md` para os outros grupos:
  escopo, regras (Microsoft RoE, ≤10 req/s, só contas próprias), contas, como gerar DPoP, o que já sabemos,
  modelo de relatório. **Não testado de verdade**: build da imagem e o deploy (fazer com `AZURE.md`).

- 10/10 (5ª sessão) — **Item 10 escrito.** **Chave no Keystore**: plugin nativo `ChaveAparelho`
  (`app/android/.../ChaveAparelhoPlugin.java`) gera a chave DPoP P-256 no Android Keystore (StrongBox se houver,
  senão TEE), assina as provas (DER → r||s) e devolve a **cadeia de atestação**; `src/lib/dpop.ts` usa o plugin no
  APK e o WebCrypto no navegador/PWA. **Atestação no lugar do Play Integrity** (que exige app na Play Store,
  projeto no Google Cloud e chamada à Google a cada login): `app/core/atestacao.py` confere a cadeia até as raízes
  da Google (fixadas pelo SPKI em `raizes_atestacao.pem`: RSA e "Key Attestation CA1"), a lista de revogação da
  Google (cache de 24 h; pega keybox vazada), que a chave atestada **é a chave DPoP** da sessão, o desafio, o pacote
  e (com `ATESTACAO_ASSINATURAS`) o certificado que assina o APK. Resultado no aparelho (`dispositivos.atestacao` =
  `strongbox`/`tee`/nulo; migração `c3d4e5f6a7b8`): atestação forjada/de outra chave/de outro app → 403; emulador,
  root ou bootloader aberto → sem nível (403 só com `ATESTACAO_EXIGIDA=1`). Testes: `test_atestacao.py` (14, com
  cadeia de teste na mesma estrutura; 203 no backend). **Pinning**: `res/xml/network_security_config.xml` base (só
  HTTPS, só CAs do sistema) e `scripts/pinos.mjs` no CI fixa as CAs da cadeia real da API + raízes reserva
  DigiCert/Microsoft, com validade de 180 dias (teste em `src/lib/pinos.test.ts`). **APK**: `allowBackup=false` e
  regras de extração (Android 12+), `FLAG_SECURE` (sem print/gravação/espelhamento: trojans bancários), WebView sem
  depuração mesmo no debug; release assinado com chave estável quando os secrets existem (`app/scripts/chave_apk.py`
  gera o PKCS12) e o SHA-256 do certificado sai no resumo do workflow. **Tokens** ficam onde estavam (memória/
  sessionStorage do WebView, privados do app): presos à chave do Keystore, copiados não servem.
  **Não verificado**: o Java só compila no CI (sem SDK nesta máquina) e nada rodou num celular. Ficou de fora: CSP
  dentro do APK (o Capacitor injeta script inline em alguns aparelhos; testar antes) e iPhone nativo (é PWA).
### Próximos passos detalhados (itens 9 e 10)

- ~~**7. Front**~~ (feito, ver diário): (a) quando o refresh falhar (401), limpar a sessão e ir para `/login` com o motivo (hoje só
  mostra erro na tela) — ver `requisitar()` em `app/src/lib/http.ts` e `useAuth`; (b) build de produção deve
  **falhar** se `VITE_API_URL` não estiver definida (senão vira modo demonstração, onde qualquer login entra) —
  checar em `vite.config.ts` com `mode === "production"`; (c) CSP e cabeçalhos para o host do front:
  `app/public/staticwebapp.config.json` (Azure Static Web Apps) com `Content-Security-Policy` (script-src
  'self' + `https://cdn.jsdelivr.net` e `https://storage.googleapis.com` que o MediaPipe usa; `connect-src` com a
  URL da API), `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(self)`.
  Overlay de debug da câmera já está só no `npm run dev` (item 1).
- ~~**8. Segredos/config**~~ (feito, ver diário): apagar a derivação de segredos do `DATABASE_URL` em `backend/entrypoint-demo.sh` (exigir
  `JWT_SECRET`/`EMBEDDING_KEY`/`ADMIN_SENHA` no ambiente) e o `CORS_ORIGIN_REGEX` de `*.netlify.app` no
  `Dockerfile` da raiz; atualizar `.env.example` com as variáveis novas (`DPOP_*`, `SESSAO_*`, `CADASTRO_MAX_IP_HORA`,
  `REFRESH_MAX_IP_15MIN`, `BENEFICIOS_HABILITADOS`); no Azure, segredos no Key Vault.
- **9. Azure + `PENTEST.md`**: Dockerfile endurecido (ver `HANDOFF-V9.md` §5), `infra/azure/` (Container Apps,
  Postgres Flexible B1ms, Key Vault, Static Web Apps, Front Door Standard com regras de rate limit), workflow com
  OIDC, e o `PENTEST.md` para os outros grupos: escopo (URLs do ambiente de pentest + APK), regras (sem DoS,
  sem atacar outros recursos — Rules of Engagement da Microsoft), contas de teste por perfil (PF, MEI, PME,
  Grande com papéis), como gerar provas DPoP para testar a API direto (`backend/tests/test_dpop.py`, classe
  `Chave`), modelo de relatório de achados. Plano de distribuição: Android = APK do CI; iPhone = PWA (Safari →
  Adicionar à Tela de Início), a menos que alguém tenha Mac + conta Apple Developer.
- **10. App nativo** (depois do APK existir): chave DPoP no Keystore/Keychain, tokens em armazenamento seguro,
  certificate pinning, Play Integrity / App Attest verificados no servidor (contra câmera virtual).
- **Pendências soltas**: testar no celular o cadastro em etapas e a prova de vida sorteada; calibrar
  `PISCADAS_EXTRAS`/`PISCADAS_NATURAIS_MAX` e `GIRO_MINIMO` num aparelho real; 1 teste intermitente visto uma
  vez (item 4).
