# Deploy senha/TOTP na assinatura Azure do Gustavo (17/10/2026)

O handoff [HANDOFF-DEPLOY-TOTP-AZURE.md](HANDOFF-DEPLOY-TOTP-AZURE.md) foi concluído numa **segunda
assinatura** (Azure for Students do Gustavo, `d84028eb-e5bb-426b-ac31-8b5aba3c8adc`), do zero, com a
`main` em `e17f5c7`. O ambiente do Alef **não foi alterado**.

## Estado
- Grupo `rg-astro-academico` (canadacentral), acesso público (sem filtro de IP).
- Front: https://astro-front.blackfield-6387536e.canadacentral.azurecontainerapps.io
- API: https://astro-api.blackfield-6387536e.canadacentral.azurecontainerapps.io
- Testado: `/saude` 200, `/pronto` ok, `POST /auth/totp` sem login = **401** (rota nova), CSP/CORS do
  front apontando para a API. O roteiro de teste da seção 5 do handoff **ainda não foi feito** no navegador.
- **PARADO para poupar crédito:** Postgres em `Stopped` e revisões da API/front desativadas.
  O Azure religa o Postgres sozinho depois de 7 dias.
- Banco novo: as contas do ambiente do Alef não existem aqui.
- O job `astro-bootstrap` ficou criado: serve de job de migração (melhoria 7.5 do handoff).

## Religar
```powershell
$az = "$HOME/.local/azure-cli/Scripts/az.bat"; $rg = 'rg-astro-academico'
& $az postgres flexible-server start -g $rg -n pg-astro-lpsmd35drh7ng
foreach ($app in 'astro-api','astro-front') {
    $rev = & $az containerapp show -g $rg -n $app --query properties.latestRevisionName -o tsv
    & $az containerapp revision activate -g $rg -n $app --revision $rev
}
```
Para desligar de novo: `postgres flexible-server stop` e `containerapp revision deactivate`.

## Subir do zero (ou uma versão nova)
Pré-requisitos neste PC:
- Azure CLI portátil: `py -m venv ~/.local/azure-cli` e `~/.local/azure-cli/Scripts/python -m pip install azure-cli pip-system-certs`
  (o `pip-system-certs` é necessário porque a rede intercepta HTTPS; sem ele, `CERTIFICATE_VERIFY_FAILED`).
- `az login --use-device-code` com a conta do Gustavo.
- Segredos em `.azure-local/students-secrets.clixml` (gerados na 1ª execução, DPAPI: só este usuário
  neste PC). **Não apagar:** sem eles, os dados cifrados no banco atual ficam ilegíveis.

```powershell
$sub = 'd84028eb-e5bb-426b-ac31-8b5aba3c8adc'
# 1. infraestrutura (rede, Postgres privado, ACR, Key Vault, ambiente)
.\infra\azure\Preparar-Students.ps1 -Operacao create -Assinatura $sub -AcessoPublico
# 2. imagens: ACR Tasks é bloqueado no Students, então o build roda com kaniko num job
.\infra\azure\Construir-Imagens.ps1 -Alvo api
.\infra\azure\Construir-Imagens.ps1 -Alvo front
# 3. bootstrap/migração do banco, sem publicar a API
$acr = 'acrastrolpsmd35drh7ng.azurecr.io'; $sha = git rev-parse origin/main
.\infra\azure\Preparar-Students.ps1 -Operacao create -Assinatura $sub -AcessoPublico `
    -Imagem "$acr/astro-api:$sha" -ImagemFront "$acr/astro-front:$sha" -Bootstrap -SomenteBootstrap
az containerapp job start -g rg-astro-academico -n astro-bootstrap
# 4. quando a execução terminar como Succeeded, publicar a API
.\infra\azure\Preparar-Students.ps1 -Operacao create -Assinatura $sub -AcessoPublico `
    -Imagem "$acr/astro-api:$sha" -ImagemFront "$acr/astro-front:$sha" -Bootstrap
```
`Preparar-Students.ps1` continua com a assinatura do Alef como padrão; `-Assinatura` troca o alvo.

## Custo
Parado: cerca de US$ 8–10/mês (ACR Basic + disco do Postgres + logs). Ligado: cerca de US$ 20–25/mês;
API e front escalam a zero sem uso. Para zerar: `az group delete -n rg-astro-academico` (o Key Vault fica
7 dias em soft delete; antes de recriar, rodar `az keyvault purge -n kv-astro-lpsmd35drh7ng`).
