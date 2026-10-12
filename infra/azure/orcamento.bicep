// Aplicar ANTES dos serviços no mesmo resource group.
// Valor na moeda de faturamento da assinatura. Alerta não interrompe cobrança.
targetScope = 'resourceGroup'

@minValue(1)
param valorMensal int

@minLength(1)
param emails array

@description('Primeiro dia do mês em UTC, ex.: 2026-10-01T00:00:00Z.')
param inicio string

@description('Fim do projeto em UTC; deve ser posterior ao início.')
param fim string

resource orcamento 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: 'astro-academico-mensal'
  properties: {
    category: 'Cost'
    amount: valorMensal
    timeGrain: 'Monthly'
    timePeriod: { startDate: inicio, endDate: fim }
    notifications: {
      gasto50: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 50, thresholdType: 'Actual', contactEmails: emails, locale: 'pt-br' }
      gasto75: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 75, thresholdType: 'Actual', contactEmails: emails, locale: 'pt-br' }
      gasto90: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 90, thresholdType: 'Actual', contactEmails: emails, locale: 'pt-br' }
      gasto100: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 100, thresholdType: 'Actual', contactEmails: emails, locale: 'pt-br' }
      previsao100: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 100, thresholdType: 'Forecasted', contactEmails: emails, locale: 'pt-br' }
    }
  }
}

output nomeOrcamento string = orcamento.name
