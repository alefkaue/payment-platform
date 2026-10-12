# Endurecer o Key Vault — Private Endpoint (proposta pronta pra validar)

**Status:** proposta de segurança. **NÃO aplicada ao `main.bicep`** porque não foi possível validar aqui
(sem `az`/`bicep`), e um erro de faixa de sub-rede quebraria o deploy. Aplicar só depois de
`az bicep build` passar. Alinha o Key Vault ao mesmo nível do Postgres (hoje privado).

## Por quê
Hoje o Key Vault (`infra/azure/main.bicep:191`) usa **RBAC** mas fica com **rede pública aberta** — é
alcançável pela internet (protegido por permissão, não por rede). O Postgres já é privado
(`publicNetworkAccess: Disabled` + VNet). O mais seguro é deixar o Key Vault **só acessível pela VNet**.

## O que adicionar (revisar faixas e validar antes de aplicar)

### 1. Sub-rede de Private Endpoint (no recurso `vnet`, array `subnets`)
```bicep
{
  name: 'pe'
  properties: {
    addressPrefix: redePe        // nova faixa /24 DENTRO de 10.20.0.0/16 SEM sobrepor redeApi/redeBanco
    privateEndpointNetworkPolicies: 'Disabled'
  }
}
```
> Adicionar o parâmetro `redePe` (ex.: `'10.20.3.0/24'`) conferindo que não colide com `redeApi`/`redeBanco`.

### 2. Zona DNS privada do Key Vault + link com a VNet
```bicep
resource dnsKv 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
}
resource dnsKvLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsKv
  name: 'vnet-${nome}'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: vnet.id } }
}
```

### 3. Private Endpoint do Key Vault + grupo de zona DNS
```bicep
resource peKv 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-kv-${nome}'
  location: local
  properties: {
    subnet: { id: '${vnet.id}/subnets/pe' }
    privateLinkServiceConnections: [{
      name: 'kv'
      properties: { privateLinkServiceId: kv.id, groupIds: ['vault'] }
    }]
  }
}
resource peKvDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: peKv
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [{ name: 'vault', properties: { privateDnsZoneId: dnsKv.id } }]
  }
}
```

### 4. Fechar a rede pública do Key Vault (no recurso `kv`, dentro de `properties`)
```bicep
publicNetworkAccess: 'Disabled'
networkAcls: { bypass: 'AzureServices', defaultAction: 'Deny' }
```

## Validar ANTES de aplicar
```bash
az bicep build --file infra/azure/main.bicep      # tem que passar sem erro
# conferir que redePe NÃO sobrepõe redeApi/redeBanco (az network vnet subnet list, ou no portal)
az deployment group what-if -g <rg> -f infra/azure/main.bicep   # revisar o diff antes do deploy
```

## Cuidados
- A API (Container Apps, sub-rede `api` delegada) já fica na VNet; com o Private Endpoint + a zona DNS,
  ela resolve o KV pelo IP privado. **Sem** a zona DNS correta, a API não acha o KV e o deploy sobe quebrado.
- O pipeline/CI que aplica o Bicep (ou quem roda `az acr build`) também precisa de acesso — avaliar
  `bypass: AzureServices` e/ou exceção temporária durante o deploy.
- Depois de aplicar, **testar** que a API lê os segredos (sobe sem erro de Key Vault) antes de declarar pronto.
