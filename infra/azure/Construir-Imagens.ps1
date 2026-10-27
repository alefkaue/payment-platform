# Constrói astro-api/astro-front DENTRO do Azure com kaniko, sem Docker local.
# O Azure for Students bloqueia ACR Tasks (az acr build: TasksOperationsNotAllowed);
# aqui um job temporário do Container Apps puxa o commit do GitHub (repo público) e envia ao ACR.
# Uso: .\infra\azure\Construir-Imagens.ps1 -Alvo api   (depois -Alvo front; podem rodar em paralelo)
param(
    [Parameter(Mandatory)][ValidateSet('api','front')][string]$Alvo,
    [string]$Sha = '',
    [string]$Ramo = 'main',
    [string]$Grupo = 'rg-astro-academico'
)
$ErrorActionPreference = 'Stop'
# Chama o Python do CLI direto: o az.bat/az.cmd estraga aspas e '%' vindos do PowerShell 5.1.
$py = 'C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe'
if (-not (Test-Path -LiteralPath $py)) { $py = Join-Path $HOME '.local/azure-cli/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $py)) { $py = Join-Path $HOME '.local/azure-cli/python.exe' }  # CLI em zip
function az { & $py -m azure.cli @args }
function Checar($t) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $t" } }

if (-not $Sha) { $Sha = (git -C (Join-Path $PSScriptRoot '../..') rev-parse "origin/$Ramo").Trim() }
$acrNome = az acr list -g $Grupo --query '[0].name' -o tsv; Checar 'ACR'
$acr = "$acrNome.azurecr.io"
$ambiente = az containerapp env show -g $Grupo -n cae-astro --query '{id:id,dominio:properties.defaultDomain,local:location}' -o json | ConvertFrom-Json; Checar 'ambiente'
$apiUrl = "https://astro-api.$($ambiente.dominio)"
$job = "astro-build-$Alvo"
$token = "kaniko-$Alvo"

$git = "git://github.com/alefkaue/payment-platform.git#refs/heads/$Ramo#$Sha"
if ($Alvo -eq 'api') {
    $kaniko = "--context=$git --context-sub-path=backend --dockerfile=Dockerfile --destination=$acr/astro-api:$Sha --snapshot-mode=redo --use-new-run"
    $cpu = 4.0; $mem = '8Gi'
} else {
    $kaniko = "--context=$git --context-sub-path=app --dockerfile=Dockerfile.students --build-arg=VITE_API_URL=$apiUrl --destination=$acr/astro-front:$Sha --snapshot-mode=redo --use-new-run"
    $cpu = 2.0; $mem = '4Gi'
}
Write-Host "==> $Alvo @ $Sha -> $acr"

# Token só de push, apagado no fim; a senha não é impressa.
try { az acr token delete -r $acrNome -n $token --yes -o none 2>$null } catch {}
$senha = az acr token create -r $acrNome -n $token --scope-map _repositories_push --query 'credentials.passwords[0].value' -o tsv --only-show-errors; Checar 'token'
$auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${token}:$senha"))
$config = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"auths":{"' + $acr + '":{"auth":"' + $auth + '"}}}'))

try { az containerapp job delete -g $Grupo -n $job --yes -o none 2>$null } catch {}
$script = 'mkdir -p /kaniko/.docker && echo $DOCKER_CFG | base64 -d > /kaniko/.docker/config.json && /kaniko/executor ' + $kaniko
# Definição em arquivo: o az confunde o "-c" do --args com uma opção dele.
$def = @{
    location = $ambiente.local
    properties = @{
        environmentId = $ambiente.id
        workloadProfileName = 'Consumption'
        configuration = @{
            triggerType = 'Manual'; replicaTimeout = 3600; replicaRetryLimit = 0
            manualTriggerConfig = @{ parallelism = 1; replicaCompletionCount = 1 }
            secrets = @(@{ name = 'dockercfg'; value = $config })
        }
        template = @{
            containers = @(@{
                name = 'kaniko'
                image = 'gcr.io/kaniko-project/executor:v1.23.2-debug'
                command = @('/busybox/sh', '-c', $script)
                env = @(@{ name = 'DOCKER_CFG'; secretRef = 'dockercfg' })
                resources = @{ cpu = $cpu; memory = $mem }
            })
        }
    }
}
$arq = Join-Path ([IO.Path]::GetTempPath()) "astro-job-$Alvo.yaml"
[IO.File]::WriteAllText($arq, ($def | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
try { az containerapp job create -g $Grupo -n $job --yaml $arq -o none --only-show-errors; Checar 'criar job' }
finally { Remove-Item -LiteralPath $arq -Force }

$exec = az containerapp job start -g $Grupo -n $job --query name -o tsv; Checar 'iniciar job'
$estado = ''
for ($i = 0; $i -lt 240; $i++) {
    Start-Sleep 15
    $estado = az containerapp job execution show -g $Grupo -n $job --job-execution-name $exec --query properties.status -o tsv
    if ($i % 4 -eq 0) { Write-Host "   $(Get-Date -Format HH:mm:ss) $estado" }
    if ($estado -in 'Succeeded', 'Failed', 'Stopped', 'Degraded') { break }
}
az acr token delete -r $acrNome -n $token --yes -o none
if ($estado -ne 'Succeeded') { throw "Build terminou como '$estado'. Job $job mantido para ver os logs (execucao $exec)." }
az containerapp job delete -g $Grupo -n $job --yes -o none
Write-Host "PRONTO: $acr/astro-${Alvo}:$Sha" -ForegroundColor Green
