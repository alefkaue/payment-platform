# PayFlow — plataforma de pagamentos com Split de IBS/CBS (v6)

Plataforma de pagamentos brasileira com **split automático de IBS/CBS** (Reforma
Tributária): toda transferência para uma conta **PJ** é dividida no ato — o imposto
vai para a conta do **Governo** e a empresa recebe o líquido. Transferências para
PF não têm retenção.

Monorepo:

```
backend/   API FastAPI + DeepFace (biometria) + Postgres/SQLite + JWT + Split
app/       App mobile (Expo / React Native) — gera APK instalável via EAS
site/      Site institucional (Next.js) — hero, calculadora de split, etc.
frontend/  [LEGADO] MVP web de página única da v5 — superado por app/ + site/
```

---

## O que mudou na v6 (esta entrega)

Esta rodada **finalizou o núcleo de produto e fechou as falhas de segurança** da
auditoria. Mapa do que foi feito, por severidade:

### 🔴 Crítico (bloqueava virar produto) — resolvido
1. **Autenticação JWT + refresh token.** Login com e-mail/senha (bcrypt), access
   token curto (15 min) e refresh longo (7 dias) com **rotação** e **detecção de
   reuso** (um refresh roubado e reapresentado derruba todas as sessões). Todos os
   endpoints sensíveis agora exigem login. `GET /usuarios` é só admin; o histórico
   de transações é filtrado por usuário.
2. **Fim do saldo grátis.** Conta nasce com saldo **zero**. Dinheiro só entra por
   **depósito** feito por admin a partir da **conta Governo** (`POST /admin/depositar`).
3. **Rate-limit** nas tentativas de login e de verificação facial (por janela de
   tempo), e as mensagens de erro **não vazam mais** distância/limite da biometria.
4. **Limite de tamanho de foto** (5 MB) validado no schema, no service e por
   middleware de borda — foto gigante não derruba mais o servidor.

### 🟠 README dizia que existia, mas não existia — agora existe
5. **`sessoes_mfa` e `logs_auditoria` são gravadas** de verdade (login, cadastro,
   transferência, depósito — sucesso e falha).
6. **Saldo inicial/depósito entra no `historico_saldo`** (ledger completo).
7. **`.env` é carregado automaticamente** (pydantic-settings) — sem `source .env`.

### 🟡 Dinheiro e dados
8. **Valores validados** (`Decimal`, 2 casas, teto) — `0,001` é rejeitado (422),
   valor gigante não estoura a coluna.
9. O método perigoso `atualizar_saldo` (mudava saldo sem trava/histórico) **foi
   removido** — todo movimento passa pelo caminho atômico com histórico.
10. **Cadastro + biometria numa transação só** (atomicidade) — não sobra conta sem
    biometria.
11. **Idempotência**: `idempotency_key` por transferência; double-click não duplica.
12. **Embedding facial cifrado** em repouso (Fernet) — LGPD, dado sensível.

### 🔵 Funcionalidades e infra
13. **Motor de Split Payment implementado** (`services/split_service.py`): CBS/IBS
    por vigência (2026 teste / 2027 cheia), com invariante testado `cbs+ibs+liq==bruto`.
14. **Testes** (pytest): 31 testes cobrindo auth, split, transferência, depósito,
    idempotência, autorização e validação.
15. **Alembic** para migrações versionadas (`backend/alembic/`).
16. **Paginação** nas listagens (`limite`/`offset`).
17. **Docker/segurança/logs**: container roda como **usuário não-root**, segredos do
    compose vêm de `.env` (não hardcoded), **CORS restrito** à lista configurada,
    **logging** ativo, migração aplicada no start do container.

---

## Arquitetura do backend (resumo)

Mudança estrutural desta versão: **um único repositório** (`repositories/repository.py`,
sobre SQLAlchemy) roda tanto em **Postgres** (produção) quanto em **SQLite**
(dev/testes) — antes havia um repositório em memória (dict) paralelo que
reimplementava tudo à mão e divergia. Agora a lógica relacional é a mesma nos dois.

```
backend/app/
  core/
    config.py          # Settings via .env (pydantic-settings)
    security.py        # bcrypt, JWT (access+refresh), cifra Fernet do embedding
  db/
    base.py            # engine Postgres OU SQLite (fallback), create_all (dev)
    models.py          # 9 tabelas (usuarios, carteiras, transacoes, refresh_tokens,
                       #  sessoes_mfa, historico_saldo, logs_auditoria,
                       #  split_regras, split_liquidacoes)
  repositories/
    repository.py      # repositório único: transfer atômico + split, idempotência,
                       #  refresh tokens, auditoria, rate-limit
  services/
    auth_service.py    # login, emissão/rotação de tokens, detecção de reuso
    usuario_service.py # cadastro (senha + biometria cifrada), saldo zero
    pagamento_service.py # transferência: dono da carteira, split, MFA por valor
    split_service.py   # motor IBS/CBS (puro, testado)
    deposito_service.py# depósito admin a partir da conta Governo
    biometria_service.py # DeepFace: liveness + reconhecimento (imports lazy)
  deps.py              # usuario_atual / admin_atual (JWT), ip_cliente
  routers/
    auth.py usuarios.py pagamentos.py admin.py
  main.py              # CORS, middleware de tamanho, lifespan (seed + conta Governo)
  alembic/             # migrações versionadas
  tests/               # pytest (SQLite in-memory, DeepFace falsificado)
```

---

## Rodando o backend

### Dev rápido (SQLite, sem Postgres)

```bash
cd backend
py -3.12 -m venv .venv && .venv/Scripts/activate   # Windows
# python3.12 -m venv .venv && source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Sem `DATABASE_URL`, usa SQLite em `backend/payflow.db`. Swagger em
http://127.0.0.1:8000/docs. No boot é criada a conta **admin/Governo**
(`admin@payflow.com.br` / senha de dev — veja o aviso no log).

> A instalação inclui `deepface` + `tensorflow` (~1-2 GB) para a biometria. Os
> imports são **lazy**: a API sobe e o resto funciona mesmo antes dos pesos
> baixarem; o download acontece na 1ª foto processada. `opencv-python` precisa de
> `libgl1`/`libglib2.0-0` no Linux.

### Testes

```bash
cd backend
pip install pytest httpx
pytest           # 31 passam (não precisam de TensorFlow nem Postgres)
```

### Produção / Docker (Postgres)

```bash
cp .env.docker.example .env   # preencha JWT_SECRET, EMBEDDING_KEY, ADMIN_SENHA, senha do Postgres
docker compose up --build
```

Gere os segredos:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"              # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # EMBEDDING_KEY
```

O container aplica as migrações Alembic (`alembic upgrade head`) antes de subir a
API e roda como usuário não-root.

---

## App mobile (`app/`) — Expo / React Native

Fluxos: Landing → Criar conta (com selfie) → Entrar → Início (saldo + transações)
→ Transferir (prévia do split em tempo real) → Comprovante → Extrato → Governo.
Transferências acima de **R$ 500** exigem selfie (MFA facial).

### Rodar em desenvolvimento (Expo Go)

```bash
cd app
npm install
# Edite app.json -> expo.extra.apiUrl para o IP da máquina que roda o backend
# (ex: http://192.168.0.10:8000 — não use 127.0.0.1, o celular não alcança)
npx expo start          # leia o QR code com o app Expo Go
```

### Gerar o APK instalável (o ".exe do celular")

Precisa de uma conta Expo (gratuita) — o build roda na nuvem (EAS), sem Android
SDK local:

```bash
cd app
npm install
npx expo login                         # sua conta Expo
npx eas-cli build -p android --profile preview
```

Ao final, o EAS devolve um **link do `.apk`** — baixe no celular e instale
(permita "instalar de fontes desconhecidas"). O perfil `preview` em `eas.json` já
está configurado para gerar APK (não AAB).

---

## Site institucional (`site/`) — Next.js

```bash
cd site
npm install
npm run dev        # http://localhost:3000
npm run build      # build de produção (testado ✓)
```

Hero, recursos, **calculadora de split interativa** (mesmo cálculo do backend),
seção de segurança, como começar, FAQ e CTA, com animações ao rolar.

---

## Endpoints principais

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| POST | `/usuarios` | público | Cadastro (saldo 0, biometria) |
| POST | `/auth/login` | público | Login → access + refresh |
| POST | `/auth/refresh` | público | Rotaciona o refresh token |
| POST | `/auth/logout` | público | Revoga o refresh |
| GET | `/usuarios/eu` | usuário | Minha conta (com saldo) |
| GET | `/usuarios/{id}` | usuário | Consulta carteira (saldo só p/ dono/admin) |
| GET | `/usuarios` | admin | Lista contas (paginado) |
| POST | `/pagamentos/transferir` | usuário | Transfere (split + MFA por valor) |
| GET | `/pagamentos/transacoes` | usuário | Histórico (próprio; admin vê tudo) |
| GET | `/pagamentos/split/simular` | público | Prévia do split (calculadora) |
| POST | `/admin/depositar` | admin | Deposita a partir da conta Governo |
| GET | `/admin/governo/retencoes` | admin | Total de IBS/CBS retido |

---

## O que ainda fica para depois

- Build do APK: precisa de uma conta Expo (passo manual acima).
- Pixel-perfect de todas as 11 telas do handoff — esta v6 cobre o fluxo completo
  com os tokens do design; o refino fino de cada tela continua.
- Deploy em VM Azure (o backend já é agnóstico de onde o Postgres roda).
- Liveness ativa (vídeo/desafio) — hoje é passiva por foto única.
