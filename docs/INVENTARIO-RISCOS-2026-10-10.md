# Inventário de falhas, controles e riscos — 10/10/2026

Este documento reúne o que foi identificado no projeto até esta revisão. Não é
uma lista de todas as vulnerabilidades possíveis nem um certificado de segurança.
Um risco conhecido, uma hipótese ainda não reproduzida e uma falha comprovada
são situações diferentes e estão identificadas abaixo.

Base do trabalho: código, testes, configuração local e relatórios anteriores.
O inventário de código contém 109 rotas da API, 32 tabelas ORM e 52 chaves
estrangeiras. Essa contagem não representa cobertura integral de segurança.
O [OWASP ASVS](https://owasp.org/projects/asvs) é uma referência para ampliar a
verificação de controles, não uma certificação obtida pelo projeto.

## Atualização em 11/10/2026

O objetivo atual é uma simulação: não há dinheiro real nem autenticação documental
perante emissor. API e interface informam essa condição. Azure não foi criada ou
implantada. O relatório atual está em [TRATAMENTO-RISCOS-2026-10-11.md](TRATAMENTO-RISCOS-2026-10-11.md).
O complemento desta rodada está em [PENDENCIAS-RISCOS-2026-10-11.md](PENDENCIAS-RISCOS-2026-10-11.md).
Cifragem, isolamento e preservação dos dados: [CIFRAGEM-ISOLAMENTO-2026-10-11.md](CIFRAGEM-ISOLAMENTO-2026-10-11.md).
As seções de execução e resultado de 10/10 abaixo são históricas.

| Risco | Tratamento atual | Limitação restante |
|---|---|---|
| R01/R15/R18 | Simulação declarada na API/interface; produção não aprova automaticamente autenticidade documental | Não autentica documentos nem liquida Pix real; histórico não foi reclassificado |
| R02 | Segredos de webhook e dados pessoais cifrados; migração, rotação e restauração verificadas | Dados cadastrais e conteúdos sensíveis agora cifrados; valores financeiros/metadados continuam visíveis onde necessários; comprometimento do host com chaves permite leitura |
| R03 | RLS em 8 grupos de objetos internos; escrita de usuários/vínculos exige contexto assinado; privilégios e conciliação conferidos | Carteiras/ledger não têm RLS integral; tarefas de sistema e comprometimento da API/chaves conservam alcance amplo |
| R04/R11 | Controles existentes preservados; stub facial continua proibido em produção | Resistência a ataques físicos e artefato nativo em aparelhos exigem validação |
| R05 | Template preparado com origem privada, Front Door Premium e regras WAF gerenciadas | Sem compilação Bicep ou implantação; aprovação da conexão privada e validação operacional pendentes |
| R06/R13 | Backups e logs brutos antigos conhecidos cifrados; arquivos/chaves com permissões restritas | Chaves no mesmo host; retenção, disco e cofre definitivo ainda exigem operação |
| R07 | Doze alterações sensíveis têm registro mínimo de auditoria na mesma transação | Outras ações e identificação completa do ator ainda dependem da trilha complementar |
| R08 | Corrigida isenção indevida de limite em prontidão acessada externamente | Limite geral continua por processo; defesa distribuída não foi validada |
| R09 | Excesso concorrente confirmado; orçamento atômico em cadastro, refresh, recuperação, desafio facial e consulta Pix; reservas de verificações em andamento para senha, troca de senha, TOTP e rosto | Etapas complementares e limite HTTP distribuído ainda exigem avaliação; reservas abandonadas ocupam a janela |
| R10 | Validação e extração de PDF em processo separado com timeout, quotas Linux e limite de concorrência | OCR e demais bibliotecas nativas não estão completamente isolados |
| R12 | Controles CSP/DPoP preservados e dependências verificadas | Script malicioso executando na origem pode agir como a sessão |
| R14 | Backup novo cifrado e leitura verificada; conciliação sem desvios | Restauração em banco descartável verificada nesta etapa; RPO/RTO e desastre definitivo pendentes |
| R16 | Auditoria semanal e SBOM frontend preparados; audit local sem avisos, SBOM com 588 componentes | Workflow ainda não publicado; imagem, OS e APK não auditados integralmente |
| R17 | Exposição em produção bloqueada no boot, inclusive na demonstração pública | Funcionalidade exige revisão própria antes de qualquer futura habilitação |

Validação da primeira etapa de 11/10: SQLite 616 passaram/45 pulados; PostgreSQL 632 passaram/29
pulados em bancos descartáveis; privilégios/migrações 28 passaram; app 258
passaram/2 pulados. TypeScript, lint dos arquivos alterados, build HTTPS,
auditoria de privilégios e conciliação passaram. Migração ea27104b9910 aplicada
no banco local; demais tabelas preservadas. Esses conjuntos têm sobreposição.

## Novas falhas reproduzidas em 10/10

| Falha | Evidência | Correção |
|---|---|---|
| Sucesso de webhook sobrescrito por falha atrasada | Três regressões falharam antes da correção; uma entrega podia voltar a pendente/falhou | Lock de linha, contagem serializada e estado entregue preservado |
| Aprovação local sem autenticar o documento | Dois testes mostraram aprovação de KYC/KYB com dados locais que conferiam, sem prova do emissor | Produção mantém em análise; contradições claras continuam reprovadas |
| API de produção configurável em HTTP | Guard anterior verificava presença da URL, sem exigir TLS | Build exige HTTPS e rejeita credenciais, query ou fragmento na URL da API |
| Ampliação descontrolada no OCR | Quatro testes interceptaram redimensionamentos excessivos antes da alocação | Imagem resultante limitada a 2400 por lado e 4 milhões de pixels |
| Mudança de conta antes da chamada HTTP ou entre consultas de uma operação | Teste reproduziu mudança de contexto no adiamento da camada API; regressões adicionais cobrem depósito e extrato compostos | Esperas desnecessárias removidas no modo API e contexto conservado nas operações financeiras/consultas compostas principais |

O teste de webhook no PostgreSQL também confere 12 resultados concorrentes,
preservando a contagem e o sucesso. A entrega continua sendo pelo menos uma vez:
o receptor deve deduplicar por X-PayFlow-Entrega. Não há promessa de exatamente
uma chamada HTTP ao receptor.

No site, delay já resolvia imediatamente no modo API, mas await ainda adiava a
continuação para outra microtarefa. A correção remove esse adiamento desnecessário;
não se trata de uma espera real de 800 ms no modo API. Funções compostas de conta,
extrato, comprovante, transferência, pagamento de cobrança e depósito também
conferem a identidade/conta entre as chamadas. Operações já confirmadas no servidor
não são desfeitas quando o contexto muda no navegador.

Em desenvolvimento permanece o comportamento de demonstração. Em produção,
OCR e correspondência facial deixam de aprovar automaticamente documentos.
O fluxo administrativo existente pode decidir o caso, mas a decisão precisa de
evidência de autenticidade obtida por um processo confiável. Não foi conectado
um provedor externo de autenticação documental nesta etapa.

## Correções das revisões anteriores

| Grupo | Situações corrigidas | Evidências no projeto |
|---|---|---|
| Sessões e provas de posse | Logout sem conferir a chave da sessão; DPoP com domínio errado ou URI/claims inválidos; headers sensíveis duplicados | test_dpop.py, test_pentest_20261010.py |
| Documentos e cadastro | Resolução excessiva antes do decoder; rosto divergente aprovado; homônimo no quadro societário; nomes PDF escapados escondendo conteúdo ativo | test_pentest_20261010.py |
| Contexto no site | Reenvio de pagamento após troca de conta; resposta antiga alimentando outra conta; envio depois de logout durante assinatura | http-respostas.test.ts, sessao.test.ts |
| Respostas e renovação | HTML/JSON inválido quebrando tratamento de erros; resposta de refresh substituindo tokens por valores inválidos | http-respostas.test.ts |
| Cabeçalhos do site | CSP carregando configuração diferente do build | cabecalhos-ambiente.test.ts, cabecalhos.test.ts |
| Logs | Mensagens, causas, textos e objetos brutos repassados por wrappers de exceções em produção | error-capture.test.ts; testes de logs/perímetro |
| Privilégios do banco | Acesso amplo herdado; tabelas novas automaticamente acessíveis; alteração/exclusão de trilhas e campos protegidos; acesso a migrações | politica_runtime, acesso_runtime_postgres, migracoes_privilegios |
| Perímetro | Corpos excedentes ou lentos; excesso de requisições; hosts e métodos indevidos; mensagens internas em erros | test_perimetro.py |

Os relatórios PENTEST-2026-10-10.md, RECHECAGEM-SEGURANCA-2026-10-10.md,
REVISAO-COMPLEMENTAR-2026-10-10.md e REVISAO-SEGURANCA-BANCO-2026-10-10.md
detalham os cenários. A coluna de evidências não indica teste de todos os ataques
possíveis daquele grupo.

## Registro histórico dos riscos em 10/10 (estado atual na atualização acima)

Prioridade é de preparação para produção, sem atribuição de CVSS e sem alegar
que todas as situações abaixo permitem exploração externa neste momento.

| ID | Prioridade | Situação e estado | Efeito possível | Tratamento necessário |
|---|---|---|---|---|
| R01 | Alta | Autenticidade documental: integração externa ausente; aprovação automática bloqueada nesta etapa | Um documento fabricado pode ter texto e rosto que conferem | Definir e testar autenticação perante emissor/provedor e processo de revisão com evidências |
| R02 | Alta | Dados cadastrais e segredo de webhook armazenados de forma consultável; limitação confirmada | Compromisso da credencial/host autorizado permite leitura desses campos | Criptografia de campos com chaves separadas, minimização, migração e rotação testadas |
| R03 | Alta | Papel compartilhado da API acessa registros de várias contas; sem RLS por titular | Comprometimento da API/credencial amplia o impacto para várias contas e permite DML concedido | Projetar acesso por funções/contexto autenticado e isolamento de dados preservando transferências entre titulares |
| R04 | Alta | Resistência física da biometria e taxas de falso aceite não medidas nesta auditoria | Foto, replay, deepfake ou injeção podem explorar limitações dos modelos | Ensaio com aparelhos/modelos reais, métricas e equipe independente; não usar stub em produção |
| R05 | Alta | Azure/WAF/DNS/TLS e caminho de origem ainda não validados em implantação real | Configuração pode permitir acesso que contorne o gateway ou expor serviço | Validar recursos implantados, rede privada, certificados, proxies confiáveis e bloqueio da origem direta |
| R06 | Alta | Criptografia do disco/backups, RBAC do cofre, retenção e acesso operacional sem evidência completa do ambiente definitivo | Vazamento por cópia de backup, identidade operacional ou armazenamento | Validar controles da infraestrutura, acesso mínimo, rotação e recuperação de chaves |
| R07 | Alta | Auditoria de ações pode falhar depois do commit: registrar_log registra erro e não desfaz operação | Ação confirmada sem registro na tabela de auditoria; ledger financeiro tem outro mecanismo atômico | Definir requisitos de auditoria, persistência transacional/outbox e alertas de reconciliação |
| R08 | Média/alta | Orçamento geral de requisições é por processo, com cache limitado de IPs | Várias instâncias/origens podem multiplicar o orçamento; ataques distribuídos não foram demonstrados | Limite distribuído/WAF, dimensionamento conjunto e teste de carga controlado |
| R09 | Média/alta | Limites por eventos usam contagem e gravação separadas em alguns fluxos; hipótese de excesso sob concorrência ainda não reproduzida | Rajadas podem exceder o limiar esperado | Testar disputa simultânea e, se confirmada, usar consumo atômico de orçamento |
| R10 | Média/alta | Parsers PDF, OCR e bibliotecas nativas não estão todos isolados por processo com quota total | Arquivos complexos podem consumir CPU/memória apesar dos limites existentes | Isolamento de workers, quotas de memória/CPU, timeout que interrompa o processamento e testes de arquivos adversariais |
| R11 | Alta | App nativo: atestação/pinning presentes no código, sem validação completa em aparelhos/artefato release | Divergência entre implementação e comportamento real; dispositivo comprometido | Compilar release, conferir assinatura/backup/depuração e testar aparelhos reais |
| R12 | Média/alta | DPoP não impede uso da chave por um script que já execute dentro do app | XSS/extensão/malware na origem pode agir como a sessão; não foi encontrada exploração nova de XSS nesta etapa | CSP efetiva no host, controle de scripts e dependências, testes DOM e políticas dos aparelhos |
| R13 | Média | Logs antigos com dados brutos permanecem arquivados localmente com acesso restrito | Quem obtiver acesso local autorizado pode ler conteúdo antigo | Retenção/expurgo definido pela equipe; não republicar nem guardar em Git |
| R14 | Alta | Restauração local foi ensaiada anteriormente; RPO/RTO, HA e desastre do ambiente definitivo não validados | Recuperação lenta, perda de dados ou inconsistência operacional | Ensaio de recuperação na infraestrutura definitiva, conciliação e critérios mensuráveis |
| R15 | Alta | Pix/boleto/cartão/Fisco e parte dos benefícios são simulações | Aprovação local não significa liquidação ou confirmação externa real | Integrar provedores reais, autenticar callbacks, reconciliar estados e testar indisponibilidade/repetição |
| R16 | Média | Auditorias de dependências são instantâneos; imagem final, OS e artefato Android não foram auditados integralmente nesta etapa | Vulnerabilidade em componente fora do conjunto consultado ou descoberta posteriormente | SBOM, auditoria recorrente dos artefatos e atualização acompanhada de regressões |
| R17 | Média | Catálogo de benefícios permanece fora do fluxo principal e pode ser habilitado por configuração | Compras/pontos usam etapas separadas; falhas entre etapas exigem análise específica | Manter desabilitado até revisão de atomicidade e idempotência própria para essa funcionalidade |
| R18 | Alta | Histórico de aprovações anteriores não foi reclassificado pela nova política de documentos | Promover um banco de demonstração/legado pode carregar aprovações obtidas sem autenticação documental | Separar bancos de teste/produção e revisar a proveniência das aprovações antes de liberar usuários reais |

R02/R03 são limitações arquiteturais confirmadas, não provas de que um visitante
sem credenciais consegue acessar o banco. R09 era uma hipótese em 10/10; foi reproduzido e parcialmente tratado em
11/10, conforme a atualização acima. R04/R05/R06/R11/R14 são lacunas de
validação. Não é correto marcar essas situações como corrigidas por testes locais.

O [PostgreSQL distingue privilégios de tabela e políticas por linha](https://www.postgresql.org/docs/16/ddl-rowsecurity.html).
Ativar RLS sem projetar contexto, privilégios e operações entre titulares pode
interromper fluxos legítimos; uma variável de sessão escolhida pelo mesmo papel
comprometido não constitui uma solução completa.

## Mapa de verificação

| Área | Evidência disponível | O que a evidência não cobre |
|---|---|---|
| Login, JWT, refresh, MFA, recuperação | test_auth, test_sessao, test_adv_c2_auth, test_admin_totp, test_dpop | Malware/extensões, entrega real de avisos, modelos biométricos reais |
| Autorização PF/PJ/admin/objetos | test_autorizacao_objetos, test_pj_regras_bancarias, test_adv_c1, test_v9_seguranca | Abuso com credenciais privilegiadas comprometidas e isolamento DB por titular |
| Dinheiro, limites, concorrência | test_integridade_banco, test_invariantes_financeiras, test_concorrencia*, test_adv_c*_financeiro | Liquidação externa, carga prolongada e falhas distribuídas |
| Idempotência, estorno, folha, cobrança, split | test_folha_idempotencia, test_devolucao_pix, test_cobrancas, test_split_transicao | Provedores reais e todas as combinações de estados possíveis |
| Outbox e recuperação | test_outbox_webhooks, test_conciliar_pendentes, test_webhook_estado | Receptor remoto sem deduplicação, garantia de exatamente uma entrega |
| Cadastro, documentos, uploads | test_cadastro_identidade, test_documentos, test_pentest_20261010, test_ocr_recursos | Autenticidade perante emissor e todos os arquivos malformados possíveis |
| SQL e privilégios | test_seguranca_api, test_politica_runtime, test_acesso_runtime_postgres, test_migracoes_privilegios | Administrador do DB comprometido, RLS e segurança completa da infraestrutura |
| HTTP, proxy e limites | test_perimetro, test_config_producao, test_forca_bruta | DoS/DDoS, operação do WAF implantado e tempestades distribuídas |
| Site, sessão e CSP | sessao.test, http-respostas.test, cabecalhos*.test, api-producao.test | Todos os navegadores/aparelhos, host definitivo e scripts externos comprometidos |
| Segredos/dependências | Busca dos segredos locais conhecidos em arquivos rastreados; npm audit; consulta OSV dos pacotes Python | Todos os segredos possíveis, histórico completo Git e vulnerabilidades ainda desconhecidas |

O catálogo deve ser atualizado a cada alteração de fluxo, dependência e deploy.
A conclusão adequada é que existem controles testados e riscos documentados;
não que o aplicativo ou o banco estejam invulneráveis.

## Resultados históricos da execução ampliada em 10/10

- Backend completo em SQLite: 555 passaram, 44 pulados.
- Backend completo em PostgreSQL: 570 passaram, 29 pulados. Os 599 casos
  coletados foram distribuídos por arquivo em quatro bancos descartáveis
  distintos, removidos ao final; nenhuma falha ou erro nos quatro grupos.
- Credencial restrita e migrações: 28 passaram; upgrade/downgrade/upgrade e
  alembic check passaram em banco isolado. Não houve mudança de modelos.
- Site: 257 passaram, 2 pulados. A execução simultânea com build e PostgreSQL
  teve dois timeouts de UI; os 24 casos dos arquivos afetados passaram na
  rechecagem e a suíte inteira passou com maxWorkers=2, sem alterar esses testes.
- TypeScript, ESLint dos arquivos TypeScript alterados, build com HTTPS e
  git diff --check passaram. Build real com API HTTP foi recusado.
- npm audit: zero vulnerabilidades conhecidas reportadas. OSV: 84 pacotes
  Python instalados consultados, sem avisos encontrados para as versões.
- Busca literal dos segredos locais conhecidos em arquivos rastreados: nenhum
  achado. Não foi feita auditoria completa do histórico Git.
- Banco do app: auditoria de privilégios sem desvios; conciliação sem saldos
  divergentes/negativos indevidos, históricos sem transação ou movimentos
  desbalanceados. Verificações de dados somente leitura.
- API reiniciada com as correções; prontidão e site local responderam HTTP 200.

As contagens de SQLite/PostgreSQL/permissões contêm cenários em comum e não
devem ser somadas como número de ataques distintos testados. As auditorias de
dependências são instantâneos das versões consultadas, não garantias futuras.

## Resultado histórico de 10/10

Cartão: ampliar o conhecimento de falhas do aplicativo e do banco solicitado
pelo usuário.

Status: parcial quanto à segurança completa de produção; auditoria local
descrita concluída, cinco grupos novos de falhas/gaps corrigidos e 18 riscos ou
lacunas registrados. Não é possível enumerar todas as falhas possíveis.

Commits: nenhum; alterações locais no branch atual.

Arquivos alterados nesta etapa: backend/app/repositories/repository.py,
backend/app/services/documento_service.py, backend/app/services/ocr_service.py,
backend/tests/test_webhook_estado.py, backend/tests/test_ocr_recursos.py,
backend/tests/test_pentest_20261010.py, app/scripts/cabecalhos.mjs,
app/scripts/cabecalhos.d.mts, app/vite.config.ts, app/src/lib/api.ts,
app/src/lib/http.ts, app/src/lib/api-producao.test.ts,
app/src/lib/api-contexto.test.ts e este inventário. As correções anteriores
foram preservadas. O executor de testes PostgreSQL foi mantido fora do repo.

Testes: backend SQLite 555 passaram / 44 pulados; PostgreSQL 570 passaram /
29 pulados; permissões/migrações 28 passaram; app 257 passaram / 2 pulados;
tsc, ESLint e build ok; auditoria e conciliação do banco ok.

O que NÃO foi feito e por quê: os tratamentos arquiteturais/operacionais dos
18 itens abertos não foram apresentados como correções prontas. Exigem projeto
de isolamento/criptografia, integrações reais ou evidência de infraestrutura e
aparelhos não cobertos pela execução local. Não houve alterações destrutivas
de registros de clientes, reclassificação em massa de identidades antigas,
publicação, deploy, teste destrutivo de carga ou certificação ASVS.

Problemas que vi fora do escopo: todos os riscos observados relevantes à
preparação para produção estão registrados na tabela, com hipótese e ausência
de evidência distinguidas de limitação confirmada.

Como testar na mão:

1. Abrir http://127.0.0.1:8081/; a API está em http://127.0.0.1:8765.
2. Em backend, executar pytest tests/test_webhook_estado.py
   tests/test_ocr_recursos.py tests/test_pentest_20261010.py em ambiente de
   teste. TEST_DATABASE_URL deve apontar para banco descartável, nunca para o
   banco do app, pois a fixture recria o esquema.
3. Em app, executar npx vitest run src/lib/api-producao.test.ts
   src/lib/api-contexto.test.ts src/lib/http-respostas.test.ts.
4. Para produção, confirmar que documento com dados/rosto que conferem fica
   em análise e que apenas o processo confiável de validação decide o caso.
   A alteração não revoga automaticamente aprovações históricas.
5. Conferir permissões e conciliação com scripts/auditar_runtime.py e
   scripts/verificar_banco.py usando a configuração runtime do banco do app.
