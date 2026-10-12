// Correção isolada da URL; não reprovisiona banco/rede nem expõe credenciais.
targetScope = 'resourceGroup'
param nome string = 'astro'
@secure()
param pgAppSenha string
var sufixo = uniqueString(resourceGroup().id)
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: 'kv-${nome}-${sufixo}' }
resource url 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg2://astro_app:${pgAppSenha}@pg-${nome}-${sufixo}.postgres.database.azure.com:5432/astro?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
  }
}
