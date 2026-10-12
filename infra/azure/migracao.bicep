// Complementa main.bicep com o job já previsto no workflow azure.yml.
// Não cria papéis SQL: bootstrap administrativo privado precede este job.
targetScope = 'resourceGroup'

param nome string = 'astro'
param local string = resourceGroup().location
param ambienteNome string
param acrNome string
param cofreApiNome string
param imagem string
param postgresHost string
param banco string = 'astro'

@secure()
@minLength(24)
param pgMigradorSenha string

var papelAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var papelSegredos = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var sufixo = uniqueString(resourceGroup().id)
var nomesSegredos = ['embedding-key', 'webhook-keys', 'pii-keys', 'pii-index-key', 'database-context-key']

resource ambiente 'Microsoft.App/managedEnvironments@2025-07-01' existing = { name: ambienteNome }
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: acrNome }
resource cofreApi 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: cofreApiNome }
resource segredosApi 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = [for segredo in nomesSegredos: {
  parent: cofreApi
  name: segredo
}]

resource identidade 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${nome}-migracao'
  location: local
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, identidade.id, papelAcrPull)
  properties: { roleDefinitionId: papelAcrPull, principalId: identidade.properties.principalId, principalType: 'ServicePrincipal' }
}

// Escopo por segredo: o migrador não recebe senha do admin da aplicação/JWT/URL runtime.
resource leituraApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (segredo, i) in nomesSegredos: {
  scope: segredosApi[i]
  name: guid(segredosApi[i].id, identidade.id, papelSegredos)
  properties: { roleDefinitionId: papelSegredos, principalId: identidade.properties.principalId, principalType: 'ServicePrincipal' }
}]

// A identidade da API não recebe nenhuma permissão neste cofre.
resource cofreMigrador 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${nome}-mig-${sufixo}'
  location: local
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource urlMigracao 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: cofreMigrador
  name: 'database-migration-url'
  properties: {
    value: 'postgresql+psycopg2://astro_migrator:${pgMigradorSenha}@${postgresHost}:5432/${banco}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
  }
}

resource leituraMigracao 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cofreMigrador
  name: guid(cofreMigrador.id, identidade.id, papelSegredos)
  properties: { roleDefinitionId: papelSegredos, principalId: identidade.properties.principalId, principalType: 'ServicePrincipal' }
}

var referenciasSegredos = [for segredo in nomesSegredos: {
  name: segredo
  keyVaultUrl: 'https://${cofreApiNome}${environment().suffixes.keyvaultDns}/secrets/${segredo}'
  identity: identidade.id
}]

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: '${nome}-migrate'
  location: local
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identidade.id}': {} } }
  properties: {
    environmentId: ambiente.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: [{ server: acr.properties.loginServer, identity: identidade.id }]
      secrets: concat([
        { name: 'database-migration-url', keyVaultUrl: '${cofreMigrador.properties.vaultUri}secrets/database-migration-url', identity: identidade.id }
      ], referenciasSegredos)
    }
    template: {
      containers: [{
        name: 'migrate'
        image: imagem
        resources: { cpu: json('1.0'), memory: '2Gi' }
        command: ['/bin/sh', '-ec']
        // AMBIENTE dev só neste comando; nunca inicia API nem habilita tráfego.
        // Recifragem/rotação em banco existente é manutenção separada com API parada.
        args: ['alembic upgrade head && python scripts/configurar_isolamento.py && python scripts/restringir_runtime.py && alembic check']
        env: [
          { name: 'AMBIENTE', value: 'desenvolvimento' }
          { name: 'DATABASE_URL', secretRef: 'database-migration-url' }
          { name: 'DATABASE_MIGRATION_URL', secretRef: 'database-migration-url' }
          { name: 'EMBEDDING_KEY', secretRef: 'embedding-key' }
          { name: 'WEBHOOK_KEYS', secretRef: 'webhook-keys' }
          { name: 'PII_KEYS', secretRef: 'pii-keys' }
          { name: 'PII_INDEX_KEY', secretRef: 'pii-index-key' }
          { name: 'DATABASE_CONTEXT_KEY', secretRef: 'database-context-key' }
        ]
      }]
    }
  }
  dependsOn: [pull, leituraApi, leituraMigracao, urlMigracao]
}

output jobNome string = job.name
