// Publica somente runtime: não reaplica credenciais/rede/banco já provisionados.
targetScope = 'resourceGroup'
param nome string = 'astro'
param local string = resourceGroup().location
param imagem string
param imagemFront string
param publicarApi bool = true
// Lista vazia permite acesso público; autenticação e banco privado permanecem.
param ipsTeste array
param adminEmail string
param origensExtras array = ['https://localhost']
param demonstracaoPublica bool = true
param assinaturasApk string = ''
@allowed([0, 1])
param replicasMin int = 0
@allowed([1])
param replicasMax int = 1
var sufixo = uniqueString(resourceGroup().id)
var redeApi = '10.20.0.0/23'
var segredos = ['jwt-secret', 'embedding-key', 'webhook-keys', 'pii-keys', 'pii-index-key', 'database-context-key', 'admin-senha', 'database-url']
resource ambiente 'Microsoft.App/managedEnvironments@2025-07-01' existing = { name: 'cae-${nome}' }
resource idApi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: 'id-${nome}-api' }
resource idFront 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: 'id-${nome}-front' }
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: 'acr${nome}${sufixo}' }
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: 'kv-${nome}-${sufixo}' }
var apiHost = '${nome}-api.${ambiente.properties.defaultDomain}'
var frontHost = '${nome}-front.${ambiente.properties.defaultDomain}'
resource api 'Microsoft.App/containerApps@2024-03-01' = if (publicarApi) {
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
}


output apiUrl string = 'https://${apiHost}'
output frontUrl string = 'https://${frontHost}'
