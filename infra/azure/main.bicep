// Astro — ambiente no Azure para o pentest (SEGURANCA.md item 9). Passo a passo em AZURE.md.
//
//   Internet ──► Front Door Standard + WAF (rate limit) ──► Container Apps (API, VNet)
//                                                                │  identidade gerenciada
//            Static Web Apps (app, CSP)                          ├─► Key Vault (segredos, RBAC)
//                                                                ├─► ACR (imagem)
//                                                                └─► Postgres Flexible (só rede privada)
//
// Dois passos: 1º sem `imagem` (cria rede, banco, cofre, registro, front); depois de
// `az acr build`, o 2º com `imagem` cria a API e o Front Door.

targetScope = 'resourceGroup'

@description('Prefixo dos nomes.')
param nome string = 'astro'

param local string = resourceGroup().location

@description('Static Web Apps só existe em algumas regiões.')
@allowed(['eastus2', 'westus2', 'centralus', 'westeurope', 'eastasia'])
param localFront string = 'eastus2'

@description('Imagem da API no ACR (ex.: acrastroxxxx.azurecr.io/astro-api:abc123). Vazio = 1º passo, sem API.')
param imagem string = ''

@description('Réplicas sempre ligadas. 1 evita a partida a frio (modelos da biometria); 0 economiza.')
@minValue(0)
param replicasMin int = 1

param replicasMax int = 3

param adminEmail string = 'admin@astro.app'

@description('Origens além do app web liberadas no CORS. https://localhost é o APK (Capacitor no Android).')
param origensExtras array = ['https://localhost']

// ---------- Segredos (gerados fora, ver AZURE.md; vão para o Key Vault) ----------
@secure()
@minLength(32)
param jwtSecret string

@secure()
@description('Chave Fernet (44 caracteres base64).')
@minLength(44)
param embeddingKey string

@secure()
@minLength(16)
param adminSenha string

@secure()
@description('Senha do Postgres. Só [A-Za-z0-9_-] (secrets.token_urlsafe): vai crua na DATABASE_URL e o Alembic não aceita %.')
@minLength(24)
param pgSenha string

var sufixo = uniqueString(resourceGroup().id)
var comApi = !empty(imagem)
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
var segredos = ['jwt-secret', 'embedding-key', 'admin-senha', 'database-url']

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

resource kvAdmin 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-senha'
  properties: { value: adminSenha }
}

resource kvBanco 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-url'
  properties: {
    value: 'postgresql://${pgUsuario}:${pgSenha}@${pg.properties.fullyQualifiedDomainName}:5432/${pgBanco}?sslmode=require'
  }
}

// ---------- Front (app web) ----------
resource front 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-${nome}-${sufixo}'
  location: localFront
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ---------- API ----------
resource ambiente 'Microsoft.App/managedEnvironments@2024-03-01' = {
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
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}

resource fd 'Microsoft.Cdn/profiles@2024-02-01' = if (comApi) {
  name: 'afd-${nome}-${sufixo}'
  location: 'global'
  sku: { name: 'Standard_AzureFrontDoor' }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = if (comApi) {
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
            { name: 'CNPJ_PROVEDOR', value: 'brasilapi' }
            { name: 'DOCUMENTO_PROVEDOR', value: 'tesseract' }
            { name: 'ADMIN_EMAIL', value: adminEmail }
            { name: 'CORS_ORIGINS', value: join(concat(['https://${front.properties.defaultHostname}'], origensExtras), ',') }
            // O proxy de entrada do Container Apps fica na sub-rede da API; o Front Door
            // é reconhecido pelo id do perfil (app/deps.py:ip_cliente).
            { name: 'PROXIES_CONFIAVEIS', value: redeApi }
            { name: 'FRONT_DOOR_ID', value: fd!.properties.frontDoorId }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'EMBEDDING_KEY', secretRef: 'embedding-key' }
            { name: 'ADMIN_SENHA', secretRef: 'admin-senha' }
          ]
          probes: [
            // Partida: migrações + carga dos modelos podem levar ~1 min.
            {
              type: 'Startup'
              httpGet: { path: '/saude', port: 8000 }
              periodSeconds: 10
              failureThreshold: 18
            }
            {
              type: 'Liveness'
              httpGet: { path: '/saude', port: 8000 }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/saude', port: 8000 }
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: { minReplicas: replicasMin, maxReplicas: replicasMax }
    }
  }
  dependsOn: [acrPull, kvLeitura, kvJwt, kvEmbedding, kvAdmin, kvBanco, pgDb]
}

// ---------- Front Door + WAF na frente da API ----------
resource waf 'Microsoft.Network/FrontDoorWebApplicationFirewallPolicies@2024-02-01' = if (comApi) {
  name: 'waf${nome}${sufixo}'
  location: 'Global'
  sku: { name: 'Standard_AzureFrontDoor' }
  properties: {
    policySettings: {
      enabledState: 'Enabled'
      mode: 'Prevention'
      requestBodyCheck: 'Enabled'
    }
    // O tier Standard não tem as regras gerenciadas (OWASP/bots, só no Premium);
    // ficam os limites por IP. A API tem os próprios limites no banco (SEGURANCA.md item 4).
    customRules: {
      rules: [
        {
          name: 'LimiteAutenticacao'
          priority: 10
          enabledState: 'Enabled'
          ruleType: 'RateLimitRule'
          rateLimitDurationInMinutes: 1
          rateLimitThreshold: 30
          action: 'Block'
          matchConditions: [
            {
              matchVariable: 'RequestUri'
              operator: 'RegEx'
              matchValue: ['/(auth|biometria|identidade)/']
              transforms: ['Lowercase']
            }
          ]
        }
        {
          name: 'LimiteGeral'
          priority: 20
          enabledState: 'Enabled'
          ruleType: 'RateLimitRule'
          rateLimitDurationInMinutes: 1
          rateLimitThreshold: 300
          action: 'Block'
          matchConditions: [
            {
              matchVariable: 'RequestUri'
              operator: 'Any'
              matchValue: []
            }
          ]
        }
      ]
    }
  }
}

resource fdEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = if (comApi) {
  parent: fd
  name: '${nome}-api-${sufixo}'
  location: 'global'
  properties: { enabledState: 'Enabled' }
}

resource fdOrigens 'Microsoft.Cdn/profiles/originGroups@2024-02-01' = if (comApi) {
  parent: fd
  name: 'api'
  properties: {
    loadBalancingSettings: { sampleSize: 4, successfulSamplesRequired: 3, additionalLatencyInMilliseconds: 50 }
    healthProbeSettings: {
      probePath: '/saude'
      probeRequestType: 'GET'
      probeProtocol: 'Https'
      probeIntervalInSeconds: 100
    }
  }
}

resource fdOrigem 'Microsoft.Cdn/profiles/originGroups/origins@2024-02-01' = if (comApi) {
  parent: fdOrigens
  name: 'container-app'
  properties: {
    hostName: api!.properties.configuration.ingress.fqdn
    originHostHeader: api!.properties.configuration.ingress.fqdn
    httpsPort: 443
    priority: 1
    weight: 1000
    enforceCertificateNameCheck: true
  }
}

resource fdRota 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-02-01' = if (comApi) {
  parent: fdEndpoint
  name: 'api'
  properties: {
    originGroup: { id: fdOrigens.id }
    supportedProtocols: ['Https']
    httpsRedirect: 'Disabled'
    forwardingProtocol: 'HttpsOnly'
    linkToDefaultDomain: 'Enabled'
    patternsToMatch: ['/*']
  }
  dependsOn: [fdOrigem]
}

resource fdWaf 'Microsoft.Cdn/profiles/securityPolicies@2024-02-01' = if (comApi) {
  parent: fd
  name: 'waf'
  properties: {
    parameters: {
      type: 'WebApplicationFirewall'
      wafPolicy: { id: waf.id }
      associations: [{ domains: [{ id: fdEndpoint.id }], patternsToMatch: ['/*'] }]
    }
  }
}

output acr string = acr.properties.loginServer
output keyVault string = kv.name
output frontNome string = front.name
output frontUrl string = 'https://${front.properties.defaultHostname}'
@description('URL pública da API (vai em ASTRO_API_URL / VITE_API_URL).')
output apiUrl string = comApi ? 'https://${fdEndpoint!.properties.hostName}' : ''
output apiOrigemDireta string = comApi ? 'https://${api!.properties.configuration.ingress.fqdn}' : ''
