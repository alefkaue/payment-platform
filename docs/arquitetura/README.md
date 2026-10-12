# Diagramas de arquitetura (Azure)

Abrir em **https://excalidraw.com** (arraste o arquivo pra tela). São **3 versões** — repare no status
de cada uma, porque **nem toda é o que a infra realmente cria**:

| Arquivo | Status | O que mostra |
|---|---|---|
| `azure-conforme-bicep.excalidraw` | ✅ **REAL** (fiel ao `infra/azure/main.bicep`) | O que o template de fato cria — use este como referência de deploy |
| `azure-endurecida.excalidraw` | 🟠 **PROPOSTA** (ideal/didático) | Defesa em camadas "no máximo" (ex.: Private Endpoint em tudo) |
| `azure-base.excalidraw` | 🟠 **PROPOSTA** (simplificada) | Visão simples pra entender o conceito |

## O que o Bicep realmente faz (resumo do `azure-conforme-bicep`)
- **Frontend → Azure Static Web Apps** (separado) — não fica junto da API no Container Apps.
- **Só a API → Azure Container Apps**, dentro de uma **VNet** (sub-rede `aca` delegada).
- **Front Door (Premium) + WAF em `Prevention`** na frente da API.
- **Postgres Flexible** com **VNet integration** (sub-rede `banco` delegada + DNS privado) e
  **`publicNetworkAccess: Disabled`** — privado, mas **não** é "Private Endpoint".
- **Key Vault** com **RBAC** e **endpoint público** (protegido por permissão, **sem** Private Endpoint).
- **ACR** + **Managed Identity** (AcrPull + leitura do Key Vault) + **Log Analytics**.

## Diferença entre a PROPOSTA endurecida e o REAL
A proposta endurecida coloca **tudo** atrás de Private Endpoint e o front também privado. O Bicep já é
seguro (WAF Prevention, Postgres sem rede pública, RBAC no Key Vault), mas se quiserem o "máximo",
faltaria: **Private Endpoint no Key Vault** (e fechar a rede pública dele) e revisar o front no SWA.
Ver [`../operacao/AZURE.md`](../operacao/AZURE.md) e `infra/azure/main.bicep`.
