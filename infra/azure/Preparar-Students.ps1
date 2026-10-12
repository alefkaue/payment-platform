param(
    [ValidateSet('validate','what-if','create')][string]$Operacao = 'validate',
    [string]$Imagem = '',
    [string]$ImagemFront = '',
    [switch]$Bootstrap,
    [switch]$SomenteBootstrap
)
$ErrorActionPreference = 'Stop'
$astroRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$astroAz = 'C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd'
$astroAccount = & $astroAz account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $astroAccount.id -ne '361ca85d-6fb7-40db-a74c-a8e650633799') { throw 'Assinatura Students inesperada.' }
$astroLocal = Join-Path $astroRoot '.azure-local'
New-Item -ItemType Directory -Force $astroLocal | Out-Null
$astroVaultFile = Join-Path $astroLocal 'students-secrets.clixml'
if (-not (Test-Path -LiteralPath $astroVaultFile)) {
    $astroSecrets = @{}
    foreach ($astroKey in @('jwtSecret','embeddingKey','webhookKeys','piiKeys','piiIndexKey','databaseContextKey','adminSenha','pgSenha','pgAppSenha','pgMigradorSenha')) {
        $astroBytes = New-Object byte[] 32
        $astroRng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $astroRng.GetBytes($astroBytes) } finally { $astroRng.Dispose() }
        $astroValue = [Convert]::ToBase64String($astroBytes).Replace('+','-').Replace('/','_')
        if ($astroKey -in @('adminSenha','pgSenha','pgAppSenha','pgMigradorSenha','jwtSecret')) { $astroValue = $astroValue.TrimEnd('=') }
        $astroSecrets[$astroKey] = ConvertTo-SecureString $astroValue -AsPlainText -Force
    }
    # Windows DPAPI: somente este usuário nesta máquina pode recuperar os valores.
    $astroSecrets | Export-Clixml -LiteralPath $astroVaultFile
}
$astroSecrets = Import-Clixml -LiteralPath $astroVaultFile
$astroParameters = @{}
foreach ($astroKey in $astroSecrets.Keys) {
    $astroPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($astroSecrets[$astroKey])
    try { $astroParameters[$astroKey] = @{value=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($astroPointer)} }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($astroPointer) }
}
$astroParameters.imagem = @{value=$Imagem}
$astroParameters.imagemFront = @{value=$ImagemFront}
$astroParameters.habilitarBootstrap = @{value=[bool]$Bootstrap}
$astroParameters.publicarApi = @{value=(-not [bool]$SomenteBootstrap)}
$astroParameters.adminEmail = @{value=$astroAccount.user.name}
$astroParameters.replicasMin = @{value=0}
$astroParameters.replicasMax = @{value=1}
$astroBody = @{'$schema'='https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#';contentVersion='1.0.0.0';parameters=$astroParameters}
$astroTemporaryFile = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($astroTemporaryFile, ($astroBody | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
    & $astroAz deployment group $Operacao --resource-group rg-astro-academico --name astro-students --template-file (Join-Path $PSScriptRoot 'students.bicep') --parameters "@$astroTemporaryFile" --only-show-errors --query '{state:properties.provisioningState,outputs:properties.outputs,error:error}'
    if ($LASTEXITCODE -ne 0) { throw 'Operacao Azure falhou; nenhum valor de segredo deve ser publicado.' }
} finally { Remove-Item -LiteralPath $astroTemporaryFile -Force }
