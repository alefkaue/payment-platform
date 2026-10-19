# Deploy Azure — Astro Payment

## O que foi feito

Configuração completa de CI/CD para deployar a API e o frontend no **Azure Container Apps** via GitHub Actions com autenticação OIDC (sem senhas no repositório).

---

## Infraestrutura Azure

| Recurso | Nome |
|---|---|
| Resource Group | `rg-astro-academico` |
| Container Registry | `acrastroaiznuxvyssyui` |
| Container App — API | `astro-api` |
| Container App — Frontend | `astro-front` |
| Container App Environment | `cae-astro` |
| Subscription | Azure for Students (`361ca85d`) |
| Tenant | `b1051c4b` |

---

## URLs de produção

- **Frontend:** https://astro-front.blackwater-4ade2c64.canadacentral.azurecontainerapps.io
- **API:** https://astro-api.blackwater-4ade2c64.canadacentral.azurecontainerapps.io

---

## Autenticação OIDC (sem secrets)

Login do GitHub Actions no Azure usa **Workload Identity Federation** — nenhuma senha ou chave fica salva no repositório.

### App Registration criado
- Nome: `astro-github-deploy`
- App ID: `773cefe6-4f68-4398-b152-10642bf50eaf`
- SP Object ID: `69f78733-14a4-451b-81eb-543dd40746d2`

### Roles atribuídas ao SP
| Role | Escopo |
|---|---|
| `AcrPush` | ACR `acrastroaiznuxvyssyui` |
| `Contributor` | Resource Group `rg-astro-academico` |

### Federated Credential
O GitHub agora envia subjects com IDs numéricos no formato novo:
```
repo:alefkaue@167534821/payment-platform@1323709507:ref:refs/heads/main
```
A federated credential foi configurada com esse subject exato.

---

## Variáveis do repositório (Settings → Variables)

| Variável | Valor |
|---|---|
| `AZURE_CLIENT_ID` | `773cefe6-4f68-4398-b152-10642bf50eaf` |
| `AZURE_TENANT_ID` | `b1051c4b-3b94-41ab-9441-e73a72342fdd` |
| `AZURE_SUBSCRIPTION_ID` | `361ca85d-6fb7-40db-a74c-a8e650633799` |
| `AZURE_RG` | `rg-astro-academico` |
| `AZURE_ACR` | `acrastroaiznuxvyssyui` |
| `ASTRO_API_URL` | `https://astro-api.blackwater-4ade2c64.canadacentral.azurecontainerapps.io` |

---

## Workflow `.github/workflows/azure.yml`

Dispara em push para `main` nos paths `backend/**`, `app/**`, `download/**` ou no próprio workflow. Também pode ser disparado manualmente.

### Job `api`
1. Checkout do código
2. Login Azure via OIDC (`azure/login@v2`)
3. Login Docker no ACR (`az acr login`)
4. `docker build + push` da imagem da API (usa `backend/Dockerfile`)
5. Migração isolada (opcional, controlada pela var `AZURE_MIGRATION_JOB`)
6. `az containerapp update` para deployar a nova revisão

### Job `front` (depende do `api`)
1. Checkout + login Azure + login ACR
2. `docker build + push` com `--build-arg VITE_API_URL` (usa `app/Dockerfile.students`)
3. `az containerapp update` para deployar o frontend

### Por que `docker build` e não `az acr build`?
O Azure for Students bloqueia **ACR Tasks** (`TasksOperationsNotAllowed`). A solução é fazer o build no runner ubuntu-latest do GitHub e fazer push direto para o ACR.

### Por que sem `az acr show`?
O comando exige role `Reader` extra. O loginServer do ACR é sempre `{nome}.azurecr.io`, então usamos a variável `ACR_SERVER: ${{ vars.AZURE_ACR }}.azurecr.io` diretamente.

---

## Fixes deployados nesta sprint

| Commit | Descrição |
|---|---|
| `d1cff3a` | Biometria: prova de vida mais tolerante a movimentos naturais |
| `6986e65` | CI: substitui `az acr build` por `docker build+push` |
| `4c6346c` | Pentest C12 (notação científica) e C05 (idempotência SQLite) |
| `58c7e08` | CI: migration job opcional + frontend via Container App |
| `58e4e7d` | CI: elimina `az acr show`, usa `ACR_SERVER` direto |

---

## Troubleshooting

### `AADSTS700213: No matching federated identity record`
O GitHub mudou o formato do subject OIDC para incluir IDs numéricos. Se o deploy parar com esse erro, rode:
```bash
az ad app federated-credential list --id 773cefe6-4f68-4398-b152-10642bf50eaf -o table
```
Compare o `subject` com o que aparece no log do job (linha `subject claim =`). Se diferir, delete e recrie a credential:
```bash
az ad app federated-credential delete --id 773cefe6-4f68-4398-b152-10642bf50eaf --federated-credential-id <id>
az ad app federated-credential create --id 773cefe6-4f68-4398-b152-10642bf50eaf --parameters fedcred.json
```

### `MissingSubscription` no az role assignment
A CLI perdeu o contexto. Faça login explicitando o tenant e passe `--subscription`:
```bash
az login --tenant b1051c4b-3b94-41ab-9441-e73a72342fdd
az role assignment create ... --subscription 361ca85d-6fb7-40db-a74c-a8e650633799
```

### `The containerapp 'astro-api' does not exist`
O SP não tem permissão `Contributor` no RG. O Azure retorna "not found" em vez de "forbidden". Atribua o role (precisa estar logado com a conta Azure for Students):
```bash
az role assignment create \
  --assignee-object-id 69f78733-14a4-451b-81eb-543dd40746d2 \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope /subscriptions/361ca85d-6fb7-40db-a74c-a8e650633799/resourceGroups/rg-astro-academico \
  --subscription 361ca85d-6fb7-40db-a74c-a8e650633799
```
