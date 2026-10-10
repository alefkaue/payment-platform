# Astro no Azure (ambiente do pentest)

**Antes do deploy:** seguir [estrutura e operação do banco](docs/BANCO.md),
provisionar os papéis separados e configurar `AZURE_MIGRATION_JOB`. A API não
aplica migrações no boot.

Infra em `infra/azure/main.bicep`, deploy contínuo em `.github/workflows/azure.yml`.
Regras do teste para os outros grupos: `PENTEST.md`. Contexto: `SEGURANCA.md` item 9.

```
Internet ──► Front Door Standard + WAF (rate limit) ──► Container Apps (API, dentro da VNet)
                                                           │ identidade gerenciada (sem senha)
Static Web Apps (app web de testes + /baixar)              ├─► Key Vault (JWT, Fernet, admin, banco)
APK Android (CI) ──► Front Door                            ├─► Container Registry (imagem)
                                                           └─► Postgres Flexible B1ms (só rede privada)
```

- **Banco sem endereço público**: só a API, na mesma VNet, enxerga o Postgres.
- **Segredos só no Key Vault**: a API lê pela identidade gerenciada; nada de segredo em variável
  de ambiente do portal, no GitHub ou na imagem.
- **Imagem** (`backend/Dockerfile`): usuário sem privilégio, código e modelos só leitura, modelos da
  biometria conferidos por SHA-256 no build (`MODELOS_DOWNLOAD=0`: o container não baixa nada),
  `AMBIENTE=producao` (o boot recusa modo de teste, segredo fraco e CORS curinga).
- **IP do cliente**: o Front Door manda `X-Azure-ClientIP` e `X-Azure-FDID`; a API só acredita
  quando o id do perfil bate (`FRONT_DOOR_ID`) e a conexão vem de proxy confiável. Isso alimenta os limites por IP da própria API.
- **Limite conhecido**: a origem do Container Apps (`apiOrigemDireta`) continua acessível sem passar
  pelo WAF (restringir só ao Front Door pede o tier Premium com Private Link). Os limites da API
  (no banco) valem dos dois jeitos. Está declarado no `PENTEST.md`.

## Custo (estimativa, conferir na calculadora do Azure)

| Recurso | Ordem de grandeza / mês |
|---|---|
| Front Door Standard (taxa base) | ~US$ 35 |
| Postgres Flexible B1ms + 32 GB | ~US$ 17 |
| Container Apps, 1 réplica sempre ligada (1 vCPU / 2 GiB, quase sempre ociosa) | ~US$ 10–30 |
| Container Registry Basic | ~US$ 5 |
| Static Web Apps Free, Key Vault, Log Analytics | centavos |

**Depois do pentest, apague tudo**: `az group delete -n rg-astro --yes`. Para economizar enquanto
não há teste, `replicasMin=0` (a API dorme; o 1º acesso leva ~1 min para carregar os modelos).

## 1. Pré-requisitos (uma vez)

```sh
az login
az account set -s "<id da assinatura>"
for p in Microsoft.App Microsoft.DBforPostgreSQL Microsoft.Cdn Microsoft.KeyVault \
         Microsoft.ContainerRegistry Microsoft.Web Microsoft.OperationalInsights Microsoft.Network; do
  az provider register -n $p
done
az group create -n rg-astro -l brazilsouth   # se a assinatura de estudante recusar a região, use eastus2
```

## 2. Segredos

Gere **uma vez** e guarde num gerenciador de senhas. Os mesmos valores vão nos dois passos do
deploy: se a `EMBEDDING_KEY` mudar, as biometrias já cadastradas não abrem mais.

```sh
cd backend
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET
.venv/Scripts/python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # EMBEDDING_KEY
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(24))"   # ADMIN_SENHA
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"   # PG_SENHA (só letras, números, - e _)
```

No shell (não salve em arquivo do repositório):

```sh
export JWT_SECRET=... EMBEDDING_KEY=... ADMIN_SENHA=... PG_SENHA=... PG_APP_SENHA=...
SEGREDOS="jwtSecret=$JWT_SECRET embeddingKey=$EMBEDDING_KEY adminSenha=$ADMIN_SENHA pgSenha=$PG_SENHA pgAppSenha=$PG_APP_SENHA"
```

## 3. Deploy da infra (dois passos)

**Passo 1**: rede, banco, cofre, registro e o Static Web Apps (ainda sem a API):

```sh
az deployment group create -g rg-astro -f infra/azure/main.bicep -p $SEGREDOS \
  --query properties.outputs
```

Anote `acr` (ex.: `acrastroxxxx.azurecr.io`) e `frontNome`.

**Imagem**: o build roda no próprio ACR, sem Docker na máquina:

```sh
ACR=acrastroxxxx   # nome, sem .azurecr.io
az acr build -r $ACR -t astro-api:inicial -f backend/Dockerfile backend
```

**Entre os passos:** criar `astro_app` e `astro_migrator` no PostgreSQL privado,
aplicar as migrações e restringir o runtime (ver `docs/BANCO.md`). O Bicep não
executa SQL de provisionamento.

**Passo 2**: a API e o Front Door:

```sh
az deployment group create -g rg-astro -f infra/azure/main.bicep -p $SEGREDOS \
  -p imagem=$ACR.azurecr.io/astro-api:inicial --query properties.outputs
```

Saídas: `apiUrl` (Front Door, vai para o app e para o APK), `apiOrigemDireta` e `frontUrl`.
Confira: `curl -s <apiUrl>/saude` → `{"status":"ok"}`. Se a revisão não subir, os logs estão em
`az containerapp logs show -g rg-astro -n astro-api --tail 100` (falta de segredo e CORS errado
aparecem com a mensagem do `config.py`).

> **Rodar o passo 2 de novo** (mudar a infra) volta a imagem para a do parâmetro: passe a última
> (`az containerapp show -g rg-astro -n astro-api --query properties.template.containers[0].image`).

## 4. GitHub Actions por OIDC (sem segredo no GitHub)

```sh
APP=$(az ad app create --display-name astro-github --query appId -o tsv)
az ad sp create --id $APP
az ad app federated-credential create --id $APP --parameters '{
  "name": "main", "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:alefkaue/payment-platform:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"] }'
az role assignment create --assignee $APP --role Contributor \
  --scope $(az group show -n rg-astro --query id -o tsv)

gh variable set AZURE_CLIENT_ID       -b $APP
gh variable set AZURE_TENANT_ID       -b $(az account show --query tenantId -o tsv)
gh variable set AZURE_SUBSCRIPTION_ID -b $(az account show --query id -o tsv)
gh variable set AZURE_RG              -b rg-astro
gh variable set AZURE_ACR             -b $ACR
gh variable set AZURE_SWA             -b <frontNome>
gh variable set ASTRO_API_URL         -b <apiUrl>
```

São **variáveis**, não segredos: nenhuma dá acesso sozinha. O que dá acesso é o token OIDC que o
GitHub emite só para workflows do branch `main` deste repositório.

Daí em diante, cada push no `main` que mexa em `backend/` ou `app/`:
- **api**: `az acr build` com o SHA do commit, job isolado de migração
  (`AZURE_MIGRATION_JOB`) e só depois nova revisão no Container Apps;
- **front**: `npm run build` com `VITE_API_URL=ASTRO_API_URL` (gera a CSP com a URL da API) e
  publica no Static Web Apps o app web (para testes) com a página de download do APK em `/baixar`.

O `android.yml` usa a mesma `ASTRO_API_URL`: o APK do CI passa a falar com o Front Door, com
certificate pinning das CAs que o Front Door apresenta (gerado no build, `app/scripts/pinos.mjs`).

**APK release (chave de assinatura estável)**, uma vez:

```sh
backend/.venv/Scripts/python.exe app/scripts/chave_apk.py   # cria ~/astro-release.p12 e imprime os secrets
gh secret set ANDROID_KEYSTORE_B64   # cole a linha base64
gh secret set ANDROID_KEYSTORE_SENHA
gh secret set ANDROID_KEY_SENHA
gh secret set ANDROID_KEY_ALIAS -b astro
```

Depois rode o passo 2 do deploy com `-p assinaturasApk=<ATESTACAO_ASSINATURAS impresso>`: a API passa
a recusar a atestação de um APK assinado por outra chave (reempacotado).

## 5. Conferências depois do deploy

- `curl -sI <frontUrl>` mostra `Content-Security-Policy`, `X-Frame-Options: DENY`, HSTS.
- `curl -s <apiUrl>/docs` → 404 (Swagger desligado em produção).
- 40 `POST <apiUrl>/auth/login` seguidos → o WAF passa a responder 429/403 depois do 30º no minuto.
- No portal, Postgres → Rede: "Acesso público: Desabilitado".
- Key Vault → Segredos: 4 itens; a identidade `id-astro-api` só tem "Key Vault Secrets User".
