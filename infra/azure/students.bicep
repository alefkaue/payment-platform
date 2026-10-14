// Variante Students autorizada: HTTPS direto em ACA; sem Front Door/WAF nem SWA.
// Banco continua privado, runtime sem DDL, modelos reais e segredos no Key Vault.
targetScope = 'resourceGroup'

@description('Prefixo dos nomes.')
param nome string = 'astro'

param local string = resourceGroup().location

@description('Imagem do frontend; vazio prepara infraestrutura sem apps.')
param imagemFront string = ''

@secure()
param pgMigradorSenha string

param habilitarBootstrap bool = false
param publicarApi bool = true
@description('Redes autorizadas a testar; ingress nega as demais.')
// Lista vazia permite acesso público; autenticação e banco privado permanecem.
param ipsTeste array

@description('Imagem da API no ACR (ex.: acrastroxxxx.azurecr.io/astro-api:abc123). Vazio = 1º passo, sem API.')
param imagem string = ''

@description('Réplicas sempre ligadas. 1 evita a partida a frio (modelos da biometria); 0 economiza.')
@minValue(0)
param replicasMin int = 0

param replicasMax int = 1

@description('Limite diário de ingestão de logs em GB; -1 desliga o limite. Não é teto financeiro e pode haver excedente.')
@minValue(-1)
param logsLimiteDiarioGb int = 1

@description('Demonstração pública com depósitos fictícios e documentos opcionais; controles de produção mantidos.')
param demonstracaoPublica bool = true

param adminEmail string = 'admin@astro.app'

@description('Origens além do app web liberadas no CORS. https://localhost é o APK (Capacitor no Android).')
param origensExtras array = ['https://localhost']

@description('SHA-256 do certificado que assina o APK release (resumo do workflow "Build APK"). Vazio = não confere.')
param assinaturasApk string = ''

// ---------- Segredos (gerados fora, ver AZURE.md; vão para o Key Vault) ----------
@secure()
@minLength(32)
param jwtSecret string

@secure()
@description('Chave Fernet (44 caracteres base64).')
@minLength(44)
param embeddingKey string

@secure()
@description('Chaves Fernet exclusivas de webhook; atual primeiro, antigas separadas por vírgula.')
@minLength(44)
param webhookKeys string

@secure()
param piiKeys string

@secure()
param piiIndexKey string

@secure()
param databaseContextKey string

@secure()
@minLength(16)
param adminSenha string

@secure()
@description('Senha bootstrap do Postgres; não é entregue à API.')
@minLength(24)
param pgSenha string

@secure()
@description('Senha do papel astro_app, criado previamente com os scripts de provisionamento. Use secrets.token_urlsafe(32).')
@minLength(24)
param pgAppSenha string

var sufixo = uniqueString(resourceGroup().id)
var comApi = !empty(imagem)
var apiHost = '${nome}-api.${ambiente.properties.defaultDomain}'
var frontHost = '${nome}-front.${ambiente.properties.defaultDomain}'
var redeApi = '10.20.0.0/23'
var redeBanco = '10.20.2.0/28'
var pgUsuario = 'astroadmin'
var pgBanco = 'astro'

// ---------- Logs ----------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${nome}-${sufixo}'
  location: local
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: logsLimiteDiarioGb }
  }
}

// ---------- Rede: a API e o banco numa VNet; o banco não tem endereço público ----------
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${nome}'
  location: local
  properties: {
    addressSpace: { addressPrefixes: ['10.20.0.0/16'] }
    subnets: [
      {
        name: 'api'
        properties: {
          addressPrefix: redeApi
          delegations: [{ name: 'aca', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'banco'
        properties: {
          addressPrefix: redeBanco
          delegations: [{ name: 'pg', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }]
        }
      }
    ]
  }
}

resource dnsBanco 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: '${nome}.private.postgres.database.azure.com'
  location: 'global'
}

resource dnsBancoLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsBanco
  name: 'vnet-${nome}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

// ---------- Banco ----------
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'pg-${nome}-${sufixo}'
  location: local
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgUsuario
    administratorLoginPassword: pgSenha
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: {
      delegatedSubnetResourceId: '${vnet.id}/subnets/banco'
      privateDnsZoneArmResourceId: dnsBanco.id
      publicNetworkAccess: 'Disabled'
    }
  }
  dependsOn: [dnsBancoLink]
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: pgBanco
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ---------- Identidade da API: lê segredos e puxa imagem, sem senha nenhuma ----------
resource idApi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${nome}-api'
  location: local
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${nome}${sufixo}'
  location: local
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

var papelAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var papelSegredosKv = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, idApi.id, papelAcrPull)
  properties: {
    roleDefinitionId: papelAcrPull
    principalId: idApi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${nome}-${sufixo}'
  location: local
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource kvLeitura 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, idApi.id, papelSegredosKv)
  properties: {
    roleDefinitionId: papelSegredosKv
    principalId: idApi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Os valores ficam só no cofre; a API recebe referências (secretRef) e lê pela identidade.
var segredos = ['jwt-secret', 'embedding-key', 'webhook-keys', 'pii-keys', 'pii-index-key', 'database-context-key', 'admin-senha', 'database-url']

resource kvJwt 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'jwt-secret'
  properties: { value: jwtSecret }
}

resource kvEmbedding 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'embedding-key'
  properties: { value: embeddingKey }
}

resource kvPii 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'pii-keys'
  properties: { value: piiKeys }
}

resource kvPiiIndex 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'pii-index-key'
  properties: { value: piiIndexKey }
}

resource kvDatabaseContext 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-context-key'
  properties: { value: databaseContextKey }
}

resource kvWebhook 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'webhook-keys'
  properties: { value: webhookKeys }
}

resource kvAdmin 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-senha'
  properties: { value: adminSenha }
}

resource kvBanco 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg2://astro_app:${pgAppSenha}@${pg.properties.fullyQualifiedDomainName}:5432/${pgBanco}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
  }
}

// ---------- API ----------
resource ambiente 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${nome}'
  location: local
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/api'
      internal: false
    }
    publicNetworkAccess: 'Enabled'
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = if (comApi && publicarApi) {
  name: '${nome}-api'
  location: local
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${idApi.id}': {} }
  }
  properties: {
    environmentId: ambiente.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: [for (ip, indice) in ipsTeste: { name: 'teste-${indice}', action: 'Allow', ipAddressRange: ip }]
      }
      registries: [{ server: acr.properties.loginServer, identity: idApi.id }]
      secrets: [for s in segredos: {
        name: s
        keyVaultUrl: '${kv.properties.vaultUri}secrets/${s}'
        identity: idApi.id
      }]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imagem
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'AMBIENTE', value: 'producao' }
            { name: 'DEMONSTRACAO_PUBLICA', value: demonstracaoPublica ? '1' : '0' }
            { name: 'DEPOSITO_DEMO', value: demonstracaoPublica ? '1' : '0' }
            { name: 'DOCUMENTO_VERIFICAR_IDENTIDADE', value: demonstracaoPublica ? '0' : '1' }
            { name: 'KYC_DOCUMENTO_OBRIGATORIO', value: demonstracaoPublica ? '0' : '1' }
            { name: 'DPOP_ORIGEM_PUBLICA', value: 'https://${apiHost}' }
            { name: 'CNPJ_PROVEDOR', value: 'brasilapi' }
            { name: 'DOCUMENTO_PROVEDOR', value: 'tesseract' }
            { name: 'ADMIN_EMAIL', value: adminEmail }
            { name: 'CORS_ORIGINS', value: join(concat(['https://${frontHost}'], origensExtras), ',') }
            // Só o proxy da rede da API pode fornecer IP encaminhado.
            { name: 'PROXIES_CONFIAVEIS', value: redeApi }
            { name: 'HTTP_HOSTS', value: apiHost }
            { name: 'HTTP_REQUISICOES_MINUTO', value: '120' }
            { name: 'BIOMETRIA_CONCORRENCIA', value: '1' }
            { name: 'ATESTACAO_ASSINATURAS', value: assinaturasApk }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'RUN_MIGRATIONS', value: '0' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'EMBEDDING_KEY', secretRef: 'embedding-key' }
            { name: 'WEBHOOK_KEYS', secretRef: 'webhook-keys' }
            { name: 'PII_KEYS', secretRef: 'pii-keys' }
            { name: 'PII_INDEX_KEY', secretRef: 'pii-index-key' }
            { name: 'DATABASE_CONTEXT_KEY', secretRef: 'database-context-key' }
            { name: 'ADMIN_SENHA', secretRef: 'admin-senha' }
          ]
          probes: [
            // Partida: migrações + carga dos modelos podem levar ~1 min.
            {
              type: 'Startup'
              httpGet: { path: '/saude', port: 8000, httpHeaders: [{ name: 'Host', value: apiHost }] }
              periodSeconds: 10
              failureThreshold: 18
            }
            {
              type: 'Liveness'
              httpGet: { path: '/saude', port: 8000, httpHeaders: [{ name: 'Host', value: apiHost }] }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/pronto', port: 8000, httpHeaders: [{ name: 'Host', value: apiHost }] }
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: { minReplicas: replicasMin, maxReplicas: replicasMax }
    }
  }
  dependsOn: [acrPull, kvLeitura, kvJwt, kvEmbedding, kvWebhook, kvPii, kvPiiIndex, kvDatabaseContext, kvAdmin, kvBanco, pgDb]
}

resource idFront 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${nome}-front'
  location: local
}
resource frontPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, idFront.id, papelAcrPull)
  properties: { roleDefinitionId: papelAcrPull, principalId: idFront.properties.principalId, principalType: 'ServicePrincipal' }
}
resource front 'Microsoft.App/containerApps@2024-03-01' = if (!empty(imagemFront)) {
  name: '${nome}-front'
  location: local
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${idFront.id}': {} }
  }
  properties: {
    environmentId: ambiente.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
        ipSecurityRestrictions: [for (ip, indice) in ipsTeste: { name: 'teste-${indice}', action: 'Allow', ipAddressRange: ip }]
      }
      registries: [{ server: acr.properties.loginServer, identity: idFront.id }]
    }
    template: {
      containers: [{ name: 'front', image: imagemFront, resources: { cpu: json('0.25'), memory: '0.5Gi' } }]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
  dependsOn: [frontPull]
}

// Identidade distinta: a API não pode ler os segredos administrativos do job.
resource idBootstrap 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (habilitarBootstrap && comApi) {
  name: 'id-${nome}-bootstrap'
  location: local
}
resource bootstrapPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (habilitarBootstrap && comApi) {
  scope: acr
  name: guid(acr.id, 'bootstrap', papelAcrPull)
  properties: { roleDefinitionId: papelAcrPull, principalId: idBootstrap!.properties.principalId, principalType: 'ServicePrincipal' }
}
resource bootstrapSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (habilitarBootstrap && comApi) {
  scope: kv
  name: guid(kv.id, 'bootstrap', papelSegredosKv)
  properties: { roleDefinitionId: papelSegredosKv, principalId: idBootstrap!.properties.principalId, principalType: 'ServicePrincipal' }
}
var chavesBootstrap = ['embedding-key', 'webhook-keys', 'pii-keys', 'pii-index-key', 'database-context-key']
var referenciasBootstrap = [for s in chavesBootstrap: { name: s, keyVaultUrl: 'https://${kv.name}${environment().suffixes.keyvaultDns}/secrets/${s}', identity: idBootstrap!.id }]
resource bootstrap 'Microsoft.App/jobs@2024-03-01' = if (habilitarBootstrap && comApi) {
  name: '${nome}-bootstrap'
  location: local
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${idBootstrap!.id}': {} } }
  properties: {
    environmentId: ambiente.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: [{ server: acr.properties.loginServer, identity: idBootstrap!.id }]
      secrets: concat([
        { name: 'admin-url', value: 'postgresql://${pgUsuario}:${pgSenha}@${pg.properties.fullyQualifiedDomainName}:5432/${pgBanco}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt' }
        { name: 'migration-url', value: 'postgresql+psycopg2://astro_migrator:${pgMigradorSenha}@${pg.properties.fullyQualifiedDomainName}:5432/${pgBanco}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt' }
        { name: 'app-password', value: pgAppSenha }
        { name: 'migration-password', value: pgMigradorSenha }
      ], referenciasBootstrap)
    }
    template: {
      containers: [{
        name: 'bootstrap'
        image: imagem
        command: ['python', 'scripts/bootstrap_students.py']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'AMBIENTE', value: 'desenvolvimento' }
          { name: 'DATABASE_ADMIN_URL', secretRef: 'admin-url' }
          { name: 'DATABASE_URL', secretRef: 'migration-url' }
          { name: 'DATABASE_MIGRATION_URL', secretRef: 'migration-url' }
          { name: 'DATABASE_APP_PASSWORD', secretRef: 'app-password' }
          { name: 'DATABASE_MIGRATION_PASSWORD', secretRef: 'migration-password' }
          { name: 'EMBEDDING_KEY', secretRef: 'embedding-key' }
          { name: 'WEBHOOK_KEYS', secretRef: 'webhook-keys' }
          { name: 'PII_KEYS', secretRef: 'pii-keys' }
          { name: 'PII_INDEX_KEY', secretRef: 'pii-index-key' }
          { name: 'DATABASE_CONTEXT_KEY', secretRef: 'database-context-key' }
        ]
      }]
    }
  }
  dependsOn: [bootstrapPull, bootstrapSecrets, pgDb, kvEmbedding, kvWebhook, kvPii, kvPiiIndex, kvDatabaseContext]
}

output acr string = acr.properties.loginServer
output acrNome string = acr.name
output keyVault string = kv.name
output ambienteNome string = ambiente.name
output postgresHost string = pg.properties.fullyQualifiedDomainName
output postgresNome string = pg.name
output frontUrl string = 'https://${frontHost}'
output apiUrl string = 'https://${apiHost}'

