# Revisão de problemas — protótipo escolar ASTRO

Data: 14/10/2026. Commit revisado: `82150dd429c192e1270366256bf4487df6f2f011`.

## Escopo

Revisão de código, integração entre app e API e execução de testes locais. O projeto é uma simulação acadêmica: os valores abaixo são fictícios.

Não foram considerados defeitos: ausência de consulta oficial de CPF/RG, comprovação real de identidade, biometria de demonstração, ausência de integração bancária real, Pix/boleto simulados e outras simplificações explicitamente documentadas. Os achados tratam de comportamento implementado que pode produzir resultados inconsistentes mesmo numa apresentação escolar.

Não foram corrigidas regras de negócio nesta revisão. Os testes adicionais usados para reprodução foram temporários; os passos e resultados estão registrados aqui.

## Prioridades

| ID | Prioridade | Problema | Evidência |
| --- | --- | --- | --- |
| R01 | Alta | Reenvio de Pix com a mesma chave pode pagar duas vezes após aprovação | Reproduzido na API |
| R02 | Alta | Operador devolve Pix acima da própria alçada sem aprovação | Reproduzido na API |
| R03 | Alta | Conflito de idempotência interrompe lote depois de pagamentos já executados | Reproduzido na API |
| R04 | Alta | Folha aparece como aprovada mesmo quando nenhum salário foi pago | API e mapeamento do app reproduzidos |
| R05 | Média | Folha pendente paga funcionário desligado após o lançamento | Reproduzido na API; regra de desligamento precisa ser explicitada |
| R06 | Média | Parcelamento pequeno aceito pelo schema termina em erro 500 | Reproduzido na API |
| R07 | Média | Histórico de aprovações omite operações que falharam, expiraram ou foram canceladas | Mapeamento/consultas reproduzidos no app |
| R08 | Média | Extrato corta o histórico em 100 operações sem paginação | Confirmado por leitura do fluxo completo |
| R09 | Baixa | Limites de quantidade são conferidos fora da transação de inserção | Análise estática; concorrência em PostgreSQL não reproduzida |
| R10 | Média | Análise de PDF recusa arquivos válidos no Windows | Reproduzido com diagnóstico do subprocesso |

As prioridades refletem o impacto na simulação, sem exigir requisitos de um banco real.

## R01 — Reenvio pode gerar um segundo pagamento

**Locais:** `backend/app/services/pagamento_service.py:183` (`transferir`), `:133` (`criar_pendente`), `:389` (execução aprovada); `backend/app/repositories/repository.py:532` (busca da transação anterior).

**Causa:** a alçada diária é calculada antes de recuperar uma transferência já feita com a mesma chave. O pagamento original já consome a alçada, então o reenvio pode mudar de caminho e criar uma pendência. A aprovação executa com outra chave, `pendente-{id}`, e debita novamente.

**Reprodução validada:**

1. Criar uma PJ com saldo de R$ 1.000 e operador com alçada de R$ 100; sem alçada diária explícita, o teto diário também é R$ 100.
2. O operador envia R$ 60 com `idempotency_key="review-reenvio"`: HTTP 200.
3. Reenviar exatamente o pedido e a chave: HTTP 202, com uma nova pendência, pois R$ 60 + R$ 60 excede o teto.
4. Outro administrador aprova a pendência: HTTP 200.
5. O destinatário recebeu **R$ 120**, embora o cliente tenha reenviado uma única intenção de pagamento.

**Impacto:** resposta perdida ou tentativa de recuperação de rede pode resultar em duplicação após aprovação.

**Correção sugerida:** resolver a idempotência antes de decidir entre pagamento direto e pendência, conferindo identidade da operação e autorização atual. Unificar o vínculo entre a chave pública, a pendência e a transação executada. Aplicar a mesma análise à folha, que também decide a aprovação antes de executar as transações dos itens.

## R02 — Devolução ignora alçada do operador

**Locais:** `backend/app/services/pagamento_service.py:429` (`devolver_pix`); `backend/app/repositories/repository.py:752` (`devolver_voluntario`).

**Causa:** a devolução confere papel, aparelho, rosto quando exigido, saldo e teto do Pix original, mas não passa por `motivo_aprovacao` nem pela checagem de alçada diária usada nas transferências.

**Reprodução validada:** PJ com R$ 1 de saldo e operador com alçada de R$ 10 recebe um Pix de R$ 100. O operador chama `POST /pagamentos/transacoes/{id}/devolver` com `{"valor":"100.00"}`. A API retorna **201**, devolve os R$ 100 e deixa a PJ com R$ 1, sem pedir aprovação.

**Impacto:** o teto de movimentação do operador deixa de valer nessa saída de dinheiro. O destino continua sendo o pagador original; não foi demonstrado desvio para uma conta arbitrária.

**Correção sugerida:** incluir devoluções no controle de alçada por operação e por dia, com um fluxo de aprovação apropriado. Se devoluções forem uma exceção deliberada, documentar a exceção e apresentá-la nas permissões da equipe.

## R03 — Lote aborta após execução parcial

**Locais:** `backend/app/services/pagamento_service.py:227` (`transferir_lote`, captura somente `HTTPException` em `:250`); `backend/app/repositories/repository.py:518`; `backend/app/main.py:148` (tratamento global de `IdempotenciaConflitanteError`). O contrato em `backend/app/routers/pagamentos.py` promete resultado próprio para cada item.

**Reprodução validada:**

1. Fazer um Pix de R$ 1 usando a chave `review-conflito`.
2. Enviar um lote com três itens para o mesmo destinatário: R$ 2 com chave nova, R$ 3 usando `review-conflito`, R$ 4 com outra chave nova.
3. O primeiro item paga R$ 2. O segundo levanta `IdempotenciaConflitanteError`, que não é capturado pelo laço.
4. A requisição inteira retorna **409**, sem a lista de resultados; o terceiro item não executa.
5. O destinatário tem **R$ 3**: R$ 1 anterior mais R$ 2 do lote aparentemente recusado.

**Impacto:** o cliente perde a confirmação dos itens já pagos, e a promessa de que um erro não para os demais é quebrada. A proteção de idempotência dos itens pagos permanece; a falha é a interrupção e a resposta incompleta.

**Correção sugerida:** traduzir esse erro de domínio em resultado de erro por item e continuar o lote. Aplicar a mesma proteção ao laço de execução da folha, que também captura apenas `HTTPException`.

## R04 — Folha aprovada não significa salários pagos

**Locais:** `backend/app/services/folha_service.py:139` (`executar` devolve erros nos resultados); `backend/app/services/pagamento_service.py:405` e `:418` (conclusão como `aprovada`); `app/src/lib/api.ts:2123` e `:2142` (resultado descartado); `app/src/routes/_app.pendentes.tsx` (selo “Aprovada”).

**Reprodução validada:** operador com alçada de R$ 10 lança uma folha de R$ 100 em uma PJ com saldo de R$ 50. Outro administrador aprova. A resposta tem `status="aprovada"`, mas `resultado.resultados[0].situacao="erro"` por saldo insuficiente. O funcionário continua com **R$ 0**.

Um teste adicional do app confirmou que `decidirPendente` recebe o resultado com erro, mas `mapPendente` o remove. A tela só apresenta a aprovação.

**Impacto:** na apresentação, o usuário pode concluir que os salários foram pagos. O mesmo problema afeta execução parcial: a informação existe no backend, mas desaparece no app.

**Correção sugerida:** distinguir aprovação de execução, preservando estado de falha/execução parcial e os resultados por funcionário. Mostrar quantos salários foram pagos, quais falharam e uma ação de repetição que conserve a idempotência dos itens já pagos.

## R05 — Desligamento não altera folha que aguarda aprovação

**Locais:** `backend/app/services/folha_service.py:75` (`_resolver_itens` verifica funcionário ativo ao lançar), `:139` (`executar` usa destinos previamente resolvidos); `backend/app/services/pagamento_service.py:405` (reutilização do payload da pendência).

**Reprodução validada:** lançar uma folha de R$ 100 acima da alçada do operador; desligar o funcionário com `DELETE /empresas/atual/funcionarios/{id}`; completar o saldo e aprovar a pendência. A API paga **R$ 100** ao funcionário desligado.

**Impacto:** remover alguém da folha não impede o pagamento ainda aguardando decisão. No lançamento direto, o mesmo funcionário inativo é recusado.

**Correção sugerida:** definir a regra explicitamente. Se desligamento deve impedir salários pendentes, revalidar o cadastro na execução. Se folhas anteriores devem permanecer válidas para acerto/rescisão, indicar na aprovação que o funcionário já foi desligado e exigir decisão consciente. Este achado não afirma que toda remuneração posterior ao desligamento é incorreta.

## R06 — Parcelamento abaixo de um centavo por parcela gera 500

**Locais:** `backend/app/schemas/pagamentos.py:70` (`CobrancaCreate`); `backend/app/services/cobranca_service.py:86` (`_dividir`) e `:128`; `backend/app/repositories/repository.py:1159`; `backend/app/db/integridade_v1.py` (`ck_cobranca_valores`).

**Reprodução validada:** `POST /cobrancas` com `{"valor":"0.01","parcelas":12,"vencimento":"2026-10-15"}` passa pela validação do pedido, mas retorna **HTTP 500**. A divisão produz onze parcelas de R$ 0 e a última de R$ 0,01. A restrição `valor > 0` do banco rejeita a inserção; o serviço não trata o `IntegrityError` desse caso.

**Impacto:** entrada permitida pela API gera erro interno em vez de orientação para ajustar o parcelamento. A transação do banco é revertida; não foi observada gravação parcial das parcelas.

**Correção sugerida:** exigir `valor_em_centavos >= parcelas` antes de gerar as cobranças e responder 400/422 com mensagem específica. Conferir também os impostos distribuídos por parcela, mantendo todas as invariantes.

## R07 — Operações desaparecem do histórico

**Locais:** `app/src/lib/api.ts:2158` (`pendentes`, consulta somente `pendente`, `aprovada`, `rejeitada`); `:2142` (mapeia outros estados para `recusada`); `backend/app/repositories/repository.py:1317` (filtro por estado).

**Evidência:** um teste do app confirmou as três URLs consultadas. O backend também produz `falhou`, `expirada`, `cancelada` e `executando`, mas esses estados não são carregados pelo histórico.

**Reprodução:** provocar falha ao aprovar uma transferência com saldo insuficiente ou deixar uma operação expirar. Ao atualizar a página de aprovações, ela some das pendentes e não entra em “Decididas”. Se uma resposta `falhou` chegar pela ação de decidir, o mapeamento a representa como “Recusada”, perdendo a distinção entre rejeição e erro de execução.

**Impacto:** o usuário perde a explicação do que aconteceu e pode relançar algo sem compreender o resultado anterior.

**Correção sugerida:** carregar todos os estados relevantes, preservar o motivo e representar separadamente recusada, cancelada, expirada, em execução e falhou. O backend já aceita listagem sem filtro quando o parâmetro de status é vazio.

## R08 — Extrato sem acesso a operações antigas

**Locais:** `app/src/lib/api.ts:711` e `:717`; `app/src/routes/_app.extrato.tsx:41` e `:48`; `backend/app/routers/pagamentos.py` (`extrato`, permite `limite` e `offset`).

**Evidência por leitura:** `transacoes_` faz uma única consulta com `limite=100`. A tela busca, filtra e soma apenas esse array; não oferece próxima página, “carregar mais” nem aviso de histórico parcial.

**Reprodução sugerida:** criar 101 transações na conta, abrir o extrato e buscar a descrição da primeira. A API pode recuperá-la com `offset=100`, mas o app não faz essa consulta. Este cenário de 101 operações não foi executado nesta revisão.

**Impacto:** a busca diz que nada foi encontrado quando a operação só está fora da janela. O “Resultado do filtro” representa um subconjunto do histórico sem indicar o limite.

**Correção sugerida:** paginação, carregamento incremental ou filtros no servidor; explicitar o período/conjunto considerado no total exibido. Há consultas semelhantes limitadas a 100 cobranças em `api.ts:1473` e `:1576` que também merecem paginação.

## R09 — Corrida nos limites de quantidade

**Locais:** `backend/app/services/pix_service.py:99` e `backend/app/repositories/repository.py:1121`; `backend/app/services/folha_service.py:50` e `backend/app/repositories/extras.py:470`.

**Evidência estática:** contar e inserir usam sessões/transações diferentes. O cadastro de chave não trava a carteira nem reconta dentro da inserção. O cadastro de funcionário não trava a empresa nem revalida o limite de funcionários ativos. As restrições únicas impedem duplicatas de chave/CPF, mas não exceder a quantidade com valores diferentes.

**Cenários de corrida:** PF com quatro chaves recebe duas criações simultâneas de chave aleatória; ambas podem ler quatro e inserir, chegando a seis. MEI sem funcionários recebe dois cadastros simultâneos de funcionários diferentes; ambos podem ler zero e ultrapassar o limite configurado de um.

**Limitação:** não houve reprodução concorrente em PostgreSQL. São caminhos de corrida identificados no código, não resultados medidos nesta revisão.

**Correção sugerida:** travar a carteira/empresa e contar/inserir na mesma transação, como já é feito em outros fluxos financeiros do projeto.

## R10 — Leitor de PDF quebra no Windows

**Locais:** `backend/app/core/arquivos.py:87` (`_executar_pdf`, ambiente reduzido passado ao subprocesso); `backend/app/core/pdf_worker.py:19` (importação do FastAPI).

**Reprodução validada:** executar os testes de PDF em Python 3.12 no Windows, com `pypdf` instalado. Um PDF sintético válido é recusado com **413 “PDF excedeu os recursos de análise”**. O diagnóstico direto mostrou que o worker termina com código 1 ao importar `asyncio.windows_events`, devido a `OSError: [WinError 10106]`.

**Causa confirmada:** o ambiente do worker contém apenas `PYTHONNOUSERSITE` e `OMP_NUM_THREADS`. Ao repetir o mesmo comando, com o mesmo PDF e adicionando somente `SystemRoot=C:\Windows`, o worker terminou com **código 0** e saída `ok`. Portanto, neste ambiente, não se trata de um PDF excessivo ou inválido.

**Impacto:** o desenvolvimento local no Windows não consegue analisar PDFs válidos. A mensagem sugere problema no arquivo quando a falha é do processo. Não foi demonstrado esse defeito no deploy Linux.

**Correção sugerida:** conservar uma lista mínima de variáveis de sistema necessárias no Windows, incluindo `SystemRoot`, sem repassar credenciais. Distinguir falha de inicialização do worker de documento que excedeu recursos. Isso trata da leitura de arquivos, não de comprovar a autenticidade de CPF/RG.

## Validação e limites da revisão

- App: `npm ci --ignore-scripts`; suíte existente com **266 testes aprovados e 2 ignorados**, em 43 arquivos aprovados e 1 ignorado.
- App: `npx tsc --noEmit` passou.
- App: build com `VITE_MODO_DEMO=1` passou. Sem configuração, o build bloqueia a execução por ausência de `VITE_API_URL`; isso é uma proteção intencional, não um achado.
- Reprodução adicional: **6 testes da API e 2 testes do app passaram**, confirmando os comportamentos descritos em R01–R07. “Passaram” significa que as asserções comprovaram os defeitos atuais, não que eles estejam corrigidos.
- Backend: Python 3.12, SQLite em memória e os stubs das fixtures existentes. A primeira tentativa com Python 3.14 falhou ao compilar `pydantic-core`; foi usado Python 3.12, compatível com a faixa documentada das dependências de visão.
- A primeira execução geral do backend apresentou falhas por dependências de imagem/PDF ausentes e scripts Unix indisponíveis no Windows. Dependências de imagem/PDF foram instaladas para uma nova execução. Os testes de instalação de containers exigem ambiente Unix e não foram usados como evidência de defeito do produto.
- Site: instalação por lockfile e `npm run build` passaram; página inicial gerada com sucesso.
- Backend, suíte existente após instalar as dependências de imagem/PDF: **658 aprovados, 59 ignorados e 5 falhas**, em 139,24 segundos. Comando: `python -m pytest --ignore=tests/test_instalacao_containers.py -o addopts= -q`. As cinco falhas são dos testes de PDF e correspondem ao problema R10; os 59 ignorados incluem verificações dependentes de PostgreSQL/condições de ambiente. Os testes temporários de reprodução foram executados separadamente.
- Sem conexão com serviço bancário real, uso de documentos reais, teste destrutivo remoto ou execução da concorrência em PostgreSQL.

## Ordem sugerida para correção

1. Corrigir duplicação por reenvio e respeitar alçadas nas devoluções (R01/R02).
2. Preservar resultados de lotes/folhas e deixar falhas visíveis (R03/R04/R07).
3. Validar parcelamento e permitir consulta de todo o extrato (R06/R08).
4. Definir comportamento da folha após desligamento e fechar as corridas de quantidade (R05/R09).
5. Ajustar a inicialização do leitor de PDF para quem desenvolve no Windows (R10).
