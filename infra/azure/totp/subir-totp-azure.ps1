# Sobe a versão senha/TOTP (commit 6543789) no Azure Students do Alef.
# 1) nova senha do admin do Postgres  2) job temporário aplica a migração do TOTP
# 3) apaga o job  4) atualiza API e front  5) confere a API.
$ErrorActionPreference = 'Stop'
# Azure CLI: o do PATH; no PC do SENAI, o portátil.
$az = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $az) { $az = 'C:\Users\40184857864\.local\azure-cli\bin\az.cmd' }
$rg  = 'rg-astro-academico'
$pg  = 'pg-astro-aiznuxvyssyui'
$acr = 'acrastroaiznuxvyssyui.azurecr.io'
$sha = '6543789ca509ce181ba21105656e82aa35afa693'
$api = 'https://astro-api.blackwater-4ade2c64.canadacentral.azurecontainerapps.io'
$job = 'astro-migra-totp'
function Passo($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Checar($t) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $t" } }

Passo 'Nova senha do admin do Postgres (astroadmin)'
$bytes = New-Object byte[] 16
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$senha = 'Az' + (($bytes | ForEach-Object { $_.ToString('x2') }) -join '') + 'x9'
& $az postgres flexible-server update -g $rg -n $pg --admin-password $senha -o none; Checar 'senha do admin'
$url = "postgresql://astroadmin:$senha@$pg.postgres.database.azure.com:5432/astro?sslmode=require"

Passo 'Criando job temporario de migracao'
$codigo = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'migrar_totp.py')))
$envId  = & $az containerapp env show -g $rg -n cae-astro --query id -o tsv; Checar 'ambiente'
$idApi  = & $az identity show -g $rg -n id-astro-api --query id -o tsv; Checar 'identidade'
& $az containerapp job delete -g $rg -n $job --yes -o none 2>$null
& $az containerapp job create -g $rg -n $job --environment $envId `
    --trigger-type Manual --replica-timeout 600 --replica-retry-limit 0 --parallelism 1 --replica-completion-count 1 `
    --image "$acr/astro-api:$sha" --cpu 0.5 --memory 1Gi `
    --mi-user-assigned $idApi --registry-server $acr --registry-identity $idApi `
    --secrets "admin-url=$url" `
    --env-vars "DATABASE_ADMIN_URL=secretref:admin-url" "CODIGO=$codigo" `
    --command python --args "-c" "import os,base64;exec(base64.b64decode(os.environ['CODIGO']))" -o none
Checar 'criar job'

Passo 'Rodando a migracao'
$exec = & $az containerapp job start -g $rg -n $job --query name -o tsv; Checar 'iniciar job'
$estado = ''
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep 10
    $estado = & $az containerapp job execution show -g $rg -n $job --job-execution-name $exec --query properties.status -o tsv
    Write-Host "   $estado"
    if ($estado -in 'Succeeded', 'Failed', 'Stopped', 'Degraded') { break }
}
& $az containerapp job delete -g $rg -n $job --yes -o none
if ($estado -ne 'Succeeded') { throw "Migracao terminou como '$estado'. A API NAO foi trocada (segue a versao antiga)." }

Passo 'Atualizando a API'
& $az containerapp update -g $rg -n astro-api --image "$acr/astro-api:$sha" -o none; Checar 'atualizar API'
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 10
    try { $r = Invoke-WebRequest -UseBasicParsing -Method Post "$api/auth/totp" -TimeoutSec 20 } catch { $r = $_.Exception.Response }
    $cod = [int]$r.StatusCode
    Write-Host "   POST /auth/totp sem login: $cod (esperado 401)"
    if ($cod -eq 401) { $ok = $true; break }
}
if (-not $ok) { throw 'A API nova nao respondeu. Me avise para eu ver os logs.' }

Passo 'Atualizando o front'
& $az containerapp update -g $rg -n astro-front --image "$acr/astro-front:$sha" -o none; Checar 'atualizar front'

Write-Host "`nPRONTO! Teste em: https://astro-front.blackwater-4ade2c64.canadacentral.azurecontainerapps.io" -ForegroundColor Green
Write-Host "Nova senha do admin do Postgres (passe para o Alef guardar): $senha" -ForegroundColor Yellow
