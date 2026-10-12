# Implantação acadêmica Azure Students — arquitetura dos diagramas

**Estado atual:** aplicação publicada na variante econômica autorizada. Consulte [Azure Students — ambiente de testes](AZURE-STUDENTS-TESTE.md) para acesso, recursos efetivamente implantados, custos e prioridades. As limitações e etapas abaixo registram a preparação do desenho original.

Preparação em 12/10/2026. Referência: `azure-conforme-bicep.excalidraw` e `infra/azure/main.bicep`. Este documento complementa o guia antigo e registra a sequência atual. Não significa que a assinatura já foi configurada.

## Diagramas lidos

| Arquivo em `docs/arquitetura/` | Status e aplicação |
|---|---|
| `azure-conforme-bicep.excalidraw` | Referência escolhida. Frontend SWA; API ACA; PostgreSQL por VNet integration; Front Door Premium/WAF; Key Vault RBAC; ACR; identidade gerenciada; logs |
| `azure-base.excalidraw` | Proposta simplificada. Junta API/frontend no ACA; não aplicar no lugar do template escolhido |
| `azure-endurecida.excalidraw` | Proposta. Junta API/frontend e desenha Private Endpoints também para banco/cofre; não aplicar como se já estivesse no Bicep |

Os textos e conexões foram lidos diretamente do JSON dos três arquivos. O diagrama conforme Bicep é uma visão resumida: o template detalha o ambiente ACA interno, rede pública desabilitada e a solicitação Private Link do Front Door. O Postgres usa integração VNet delegada/DNS privado, não Private Endpoint. O Key Vault mantém endpoint público protegido por RBAC conforme a referência.

## Estado desta preparação

- Azure CLI 2.91.0 e Bicep 0.48.1 instalados nesta máquina.
- `main.bicep`, `orcamento.bicep` e `migracao.bicep` compilaram sem erros.
- Login Microsoft concluído por device code; códigos e tokens não devem ser salvos no repositório.
- Grupo gratuito `rg-astro-academico` criado em `canadacentral`, sem serviços pagos. Região do grupo não resolve a restrição regional do frontend.
- Orçamento de proteção da assinatura inteira criado; detalhes na seção de configuração aplicada abaixo.
- Faltam liberação de região para Static Web Apps, confirmação do saldo de crédito e duração de uso antes da implantação paga. A moeda do orçamento foi confirmada como BRL.
- O atalho local `docs/Documentos.lnk` não faz parte da implantação.

Compilação verifica sintaxe/tipos; não substitui validação ARM, `what-if`, quotas, RBAC e testes na assinatura.

## Custos e limites

O projeto mantém Front Door **Premium**, como solicitado. Não foi substituído por Standard ou outra borda. Esse componente tem taxa base e pode ser o principal consumo do crédito; conferir preço final e janela de uso antes do passo que o cria. Desligar a API não elimina cobranças dos demais serviços.

1. Confirmar a oferta Azure Students e preservar o spending limit existente. Não converter para pagamento por uso para contornar restrições sem decisão do titular.
2. Criar um resource group dedicado. Aplicar `infra/azure/orcamento.bicep` antes dos serviços.
3. O orçamento usa a moeda de faturamento da assinatura e é **mensal**, não representa saldo de crédito total. Configura alertas reais em 50/75/90/100% e de previsão em 100%. Definir início no primeiro dia do mês UTC e fim após a janela do trabalho.
4. Budget não para recursos. Dados de cobrança/alertas têm atraso. Não existe garantia de teto exato com esse template.
5. Pode-se passar `replicasMin=0 replicasMax=1` ao Bicep para economizar durante testes pequenos, mantendo a arquitetura. A facial terá partida a frio. Para a banca, `replicasMin=1 replicasMax=1` evita dormir. Medir antes de aumentar.
6. `logsLimiteDiarioGb=1` configura um limite diário de ingestão de logs; não é teto financeiro, pode haver excedente e redução de coleta. Ajustar após observar volume. Retenção continua 30 dias.
7. Não aumentar CPU/memória, tier do banco ou armazenamento automaticamente. Logs, tráfego, ACR, banco e borda têm cobranças próprias.
8. Ao encerrar, revisar preservação dos dados/chaves e desprovisionar apenas recursos autorizados. Parar PostgreSQL não elimina custo de armazenamento e o serviço pode reiniciar após sete dias. Nenhuma exclusão automática foi configurada.

## Sequência de implantação

Executar a partir da raiz do repositório. Exemplos abaixo usam PowerShell e `az` no PATH; se a instalação acabou de ocorrer, reabrir o terminal ou usar `C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd`.

### 1. Autenticar e selecionar a assinatura correta

```powershell
az login --use-device-code
az account list --query '[].{Nome:name,Estado:state,Id:id}' -o table
az account set --subscription '<ID DA ASSINATURA STUDENTS>'
az account show --query '{Nome:name,Estado:state,Id:id}' -o table
```

O titular faz login/MFA no site Microsoft. Não enviar senha, token ou chaves no chat. Escolher explicitamente a assinatura; não confiar apenas na seleção padrão. Conferir saldo da oferta no portal.

### 2. Criar grupo e orçamento

Definir nome/região após conferir disponibilidade e políticas da oferta. Exemplo de grupo: `rg-astro-academico`. Registrar providers Microsoft.App, DBforPostgreSQL, Cdn, KeyVault, ContainerRegistry, Web, OperationalInsights, Network e Consumption conforme necessários; aguardar registro e conferir permissões de criação/RBAC.

```powershell
az group create --name rg-astro-academico --location '<REGIAO VALIDADA>'
az deployment group create --resource-group rg-astro-academico --name astro-orcamento --template-file infra/azure/orcamento.bicep --parameters valorMensal=<VALOR> emails='["<EMAIL>"]' inicio='<PRIMEIRO DIA DO MES UTC>' fim='<FIM UTC>'
```

Exemplos com `<...>` precisam ser preenchidos; não copiar como comandos prontos. Conferir o orçamento no Cost Management e seus destinatários. Se a oferta impedir criação pela API, configurar no portal e verificar resultado antes de seguir.

### 3. Infraestrutura base, ainda sem API/Front Door

Gerar nove parâmetros seguros persistentes, todos distintos: `jwtSecret`, `embeddingKey`, `webhookKeys`, `piiKeys`, `piiIndexKey`, `databaseContextKey`, `adminSenha`, `pgSenha`, `pgAppSenha`. As cinco chaves Fernet devem ser válidas; usar biblioteca cryptography. Gerar também a senha separada de `astro_migrator`.

Preservar em gerenciador seguro. Não reutilizar valores de CI, não imprimir segredos em logs nem colocar no Git. Usar arquivo de parâmetros privado protegido ou entrega segura ao deployment; `@secure()` protege a representação ARM, mas não elimina riscos de histórico/arquivos locais. Não regenerar as chaves no segundo deploy.

Com parâmetros privados prontos, compilar, validar e revisar o `what-if` do `main.bicep`, inicialmente com `imagem=''`. Depois aplicar. Esse passo cria VNet, banco, SWA, cofre runtime, registro, identidade e ambiente ACA. A API e a borda só são criadas quando `imagem` é fornecida.

Saídas úteis acrescentadas: `ambienteNome` e `postgresHost`. Saídas existentes: `acr` (hostname; extrair o nome do registro para CLI), `keyVault`, `frontNome` e `frontUrl`.

### 4. Build e bootstrap SQL dentro da rede privada

Build da imagem em ACR com `backend/Dockerfile`, tag do commit. Não usar a imagem/perfil do Docker Hub com stub biométrico. O build depende de download de pacotes/modelos e deve ser validado.

```powershell
az acr build --registry '<NOME ACR>' --image 'astro-api:<SHA>' --file backend/Dockerfile backend
```

O banco não é acessível diretamente pelo notebook fora da VNet. **Antes do job migrador**, executar bootstrap com uma conexão administrativa temporária dentro da rede privada, por job/host operacional sem ingress público. Essa identidade temporária não deve ser a identidade da API nem receber uso contínuo pelo CI.

Usar `infra/postgres/init-roles.sh` como contrato SQL, adaptando a execução ao PostgreSQL gerenciado: criar `astro_app` e `astro_migrator` sem superuser/CREATEDB/CREATEROLE/BYPASSRLS; `astro_app` com NOINHERIT e teto de conexões; schema público com concessões explícitas; schema `astro_privado` pertencente ao migrador; remover concessões PUBLIC excessivas. Conferir que o migrador pode configurar seus objetos/default privileges, sem entregar papel administrativo à API. Usar `backend/scripts/proteger_acesso_banco.py` para conferir/provisionar o contrato após criar os papéis. Não executar bootstrap de volume Docker às cegas em um banco Azure existente.

O método concreto de acesso/bootstrap será definido com a assinatura autenticada. Não habilitar a porta pública do banco para facilitar este passo. Esta preparação ainda não criou/executou o recurso temporário de bootstrap.

### 5. Provisionar e executar o job migrador

`infra/azure/migracao.bicep` complementa a arquitetura já prevista no workflow. Recebe `ambienteNome`, `acrNome`, `cofreApiNome`, `imagem`, `postgresHost` e `pgMigradorSenha` segura. Manter o mesmo `nome`/região do `main.bicep`.

- Cria identidade própria com AcrPull.
- Lê só os cinco segredos de criptografia/contexto necessários no cofre runtime, por RBAC no segredo.
- Guarda URL PostgreSQL do migrador em cofre separado; a API não recebe acesso.
- Não guarda senha bootstrap administrativa e não cria papéis SQL.
- Job manual com paralelismo 1, zero retries automáticos, 1 vCPU/2 GiB e timeout de 30 minutos.
- Executa Alembic, configuração do contexto RLS, restrição de privilégios e `alembic check`; não inicia uvicorn.
- `AMBIENTE=desenvolvimento` vale apenas para os scripts, que não atendem tráfego; não desliga os controles da API publicada.

Aplicar via deployment group com parâmetros privados, iniciar `astro-migrate` e esperar `Succeeded`. Se falhar, verificar logs sem divulgar connection strings e não subir a API. Conceder tempo para propagação RBAC se a primeira execução ainda não ler segredos.

**Banco novo:** não há registros legados a recifrar. **Banco existente:** fazer manutenção com API/workers parados e backup; executar também `cifrar_webhooks.py` e `cifrar_dados_pessoais.py`, conforme `docs/arquitetura/BANCO.md`. O job normal não recifra todos os dados em cada deploy. Não executar dois migradores simultâneos; paralelismo 1 é por execução, não trava global entre execuções.

O workflow atual espera no máximo cerca de 10 minutos pelo job. Se o volume exigir mais, alinhar o timeout do workflow ao job antes de habilitar deploy contínuo; não disparar outro job só porque a espera do runner terminou.

### 6. API e Front Door Premium

Reaplicar `main.bicep` com a imagem construída, exatamente os mesmos segredos e os limites de réplicas escolhidos. Validar/`what-if` antes. Isso provisiona API, Front Door Premium, WAF Prevention e solicitação Private Link.

Aprovar a conexão privada correspondente ao perfil Front Door no ambiente ACA e verificar o estado aprovado. Esperar revisão ACA pronta e borda funcional. O domínio direto da origem deve falhar pela internet. Não abrir a rede pública como correção temporária.

API usa HTTPS/TLS, DPoP, senha/face reais, modelo OpenCV, PostgreSQL privado e conta runtime. `demonstracaoPublica=true` mantém somente depósitos fictícios/documentos opcionais. `BIOMETRIA_STUB` não deve ser ligado.

### 7. Frontend, APK e deploy contínuo

Configurar GitHub OIDC/variáveis `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RG`, `AZURE_ACR`, `AZURE_SWA`, `AZURE_MIGRATION_JOB=astro-migrate` e `ASTRO_API_URL` igual à URL Front Door.

Publicar frontend SWA pelo build de `app/`; esse é o app web, não o site institucional Next.js. O workflow também copia `/baixar`. Configurar assinatura estável do APK e `assinaturasApk` quando o APK fizer parte da entrega. Validar câmera/permissões/DPoP nos dispositivos usados.

Antes de habilitar automação, completar dependência dos testes do mesmo SHA e smoke test de readiness. Atualmente os workflows de teste/deploy são independentes; isso não foi alterado nesta preparação. Para banco existente, coordenar migrações e manutenção, pois o workflow atual não para a API.

### 8. Aceite e controle de gastos

Conferir `/saude`, `/pronto`, CORS/CSP, falha do acesso direto, Postgres sem acesso público, segregação das identidades e log sem segredos. Executar cadastro/login facial com pessoa correspondente e recusa de outra pessoa, transferência persistida, idempotência, saldo insuficiente, gasto concorrente e acesso negado entre contas.

Verificar custos diariamente durante a publicação, alertas e limite de logs; antes da banca, manter a réplica aquecida. A publicação só estará concluída quando os recursos e esses fluxos forem verificados. Não considerar os templates compilados como implantação já realizada.

## Verificação da assinatura após login — 12/10/2026

O login Azure CLI foi concluído. A assinatura Azure for Students está Enabled, com `spendingLimit: On`; nenhum grupo de recursos foi encontrado. Nenhum recurso pago foi criado nesta verificação. O saldo de crédito disponível ainda não foi confirmado.

**P0 — bloqueio de implantação do frontend:** a atribuição `sys.regionrestriction` permite apenas `spaincentral`, `mexicocentral`, `northcentralus`, `canadacentral` e `italynorth`. A consulta ao provedor `Microsoft.Web`, tipo `staticSites`, retorna apenas Central US, East US 2, West US 2, West Europe e East Asia. Não há interseção. A definição de política `b86dabb9-b578-4d7b-b842-3b45e95769a1` aplica `deny` às demais regiões; suas exceções são recursos globais e diretórios B2C, não Static Web Apps. Trocar apenas `localFront` no Bicep não resolve.

Para preservar a arquitetura exigida, solicitar ao suporte Azure liberação de uma região suportada por Static Web Apps, por exemplo East US 2, ou usar uma assinatura que permita esse recurso. A aprovação pelo suporte não é garantida. Não remover a política nem substituir o frontend silenciosamente. Depois da liberação, verificar também disponibilidade e cotas de Container Apps, PostgreSQL B1ms, ACR e Private Link na região escolhida antes de criar a infraestrutura paga.

**P0 — custo fixo incompatível com tratar Students como hospedagem gratuita contínua:** a documentação Microsoft apresenta US$ 330/mês como referência ilustrativa da taxa base Front Door Premium, antes de PostgreSQL, ACR, logs, tráfego e demais consumos. Isso não é uma cotação da assinatura. A cobrança real é por hora ou fração de hora em que o perfil existe. Reduzir réplicas da API a zero não interrompe essa taxa. Para economia mantendo o desenho, usar janelas curtas de demonstração e planejar retirada dos recursos que continuam cobrando; exclusão do banco exige backup e autorização específica.

Configuração mínima proposta, ainda não aplicada: Static Web Apps Free, PostgreSQL B1ms/32 GB sem HA, ACR Basic, API Consumption com mínimo zero e máximo uma réplica (aquecer antes da demonstração), limite de logs e orçamento com alertas. Definir o valor do orçamento na moeda efetiva de faturamento após confirmar crédito e duração de uso; orçamento é alerta, não limite que bloqueia cobranças. Preservar o spending limit já ativo.

Referências de custo: [comparação de preços](https://learn.microsoft.com/en-us/azure/frontdoor/understanding-pricing), [cobrança por hora do Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/billing). Evidência de região: consultas autenticadas `az policy assignment list`, `az policy definition show` e `az provider show --namespace Microsoft.Web`, realizadas em 12/10/2026.

## Configuração aplicada com autorização de economia — 12/10/2026

- Criado o grupo `rg-astro-academico` em Canada Central, com tags de projeto acadêmico e preparação sem serviços pagos. Um grupo vazio não hospeda a aplicação.
- Criado e consultado novamente o orçamento **no escopo da assinatura inteira**, `astro-protecao-students`, sem filtro por grupo. Abrange também gastos fora do grupo do projeto.
- Valor: **R$ 10 por mês**, de 01/10/2026 até 01/10/2027. É um valor conservador de alerta escolhido para detectar consumo cedo, não uma estimativa do custo de hospedar a arquitetura. O GET de confirmação retornou `currentSpend.unit: BRL` e gasto contabilizado de R$ 0,00; o saldo de crédito ainda não foi confirmado e custos contabilizados podem atrasar.
- Alertas de gasto real em 10%, 50%, 80% e 100% (respectivamente 1, 5, 8 e 10 unidades), mais previsão em 100%, habilitados para o e-mail da conta autenticada, em português. A persistência da configuração foi verificada por GET; entrega efetiva de e-mail não foi testada.
- `spendingLimit: On` preservado. Essa proteção da oferta não é um limite personalizado de 10 e não impede consumir todo o crédito Students. Budget também não desliga recursos, e dados/alertas podem atrasar.
- Não foram criados PostgreSQL, ACR, Container Apps nem Front Door Premium. Não foi implantada a API ou o frontend, e não foram feitas mudanças para expor banco/API publicamente ou contornar a política de região. Criar apenas os componentes pagos permitidos agora consumiria crédito sem disponibilizar o desenho completo.

**Próximo passo necessário:** obter liberação de uma região suportada por Static Web Apps para preservar a arquitetura, ou decidir explicitamente uma revisão do desenho para Students. Depois, validar cotas, calcular consumo para uma janela curta e testar transferência/facial com o menor dimensionamento viável. O trabalho acadêmico continua aceitando depósitos fictícios; isso não remove requisitos de autenticação, isolamento e transferência correta.

## Referências

- [Budgets em Bicep](https://learn.microsoft.com/en-us/azure/templates/microsoft.consumption/budgets)
- [Front Door Premium e ACA privado](https://learn.microsoft.com/en-us/azure/container-apps/front-door-custom-virtual-network-private-link)
- [Container Apps Jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Budgets e atraso de avaliação](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)
- [Cobrança Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/billing)
- [Daily cap Log Analytics](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/daily-cap)
