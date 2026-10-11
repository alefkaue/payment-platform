# Rechecagem de segurança — 10/10/2026

Complemento à REVISAO-COMPLEMENTAR-2026-10-10.md, após o pedido de conferir
falhas restantes e pensar em combinações adversariais de operações.

## Falhas adicionais confirmadas e corrigidas

### Dados brutos em argumentos de console.error

A proteção anterior ocultava objetos Error, mas o wrapper ainda repassava textos
e objetos comuns para o logger. Esses argumentos também podem conter credenciais
ou dados pessoais. Em produção, todos os argumentos desse wrapper agora são
substituídos por uma mensagem genérica. Desenvolvimento conserva diagnóstico.
Os testes cobrem textos, objetos, Error, serializadores e a chamada real ao
console.error instalado. Isso não estabelece proteção de todos os destinos de
log de bibliotecas ou serviços externos.

### Troca de conta durante pagamento, renovação ou leitura da resposta

Dois testes reproduziram as falhas antes da correção: um pagamento que recebeu
401 podia ser reenviado pela conta selecionada durante a renovação; uma resposta
atrasada da conta anterior podia alimentar a tela da nova conta. O servidor
continuava verificando a autorização; o problema era a troca do contexto de uma
operação entre contas que a mesma sessão podia acessar.

O cliente agora guarda a versão da conta e da sessão por requisição, confere
esses valores depois da assinatura, da resposta, da renovação e da leitura do
corpo. Trocar de conta e voltar também invalida a requisição anterior. Uma mudança
de contexto impede o envio ainda pendente ou o reenvio automático e retorna erro
409; respostas antigas são descartadas. A mensagem da troca de conta orienta
conferir o resultado anterior antes de repetir uma operação.

Isso não cancela uma transação que já foi enviada e confirmada no servidor.
O logout conserva a revogação da sessão anterior depois da limpeza local.
Rotação normal de tokens na mesma conta continua permitida.

## Verificação e limites

- App completo: 244 testes passaram, 2 pulados.
- TypeScript, ESLint dos quatro arquivos alterados e build de produção passaram.
- git diff --check passou antes da escrita deste relatório.
- Auditoria de permissões e conciliação do banco em uso passaram novamente.
  Nenhuma escrita nos registros dos clientes foi feita nesta etapa.
- Backend e modelos não foram alterados nesta rechecagem; a validação anterior
  permanece documentada: 546 testes do backend, 96 financeiros PostgreSQL e 28 de
  permissões/migrações passaram.
- O site local respondeu HTTP 200 ao final.

A leitura adicional da recuperação de senha e do vínculo de identidade não
produziu outra falha confirmada nesta etapa. A revisão não é exaustiva, não testa
a implantação definitiva e não garante ausência de vulnerabilidades desconhecidas.
As limitações da revisão anterior continuam válidas.

## Resultado

Cartão: rechecagem de falhas restantes e combinações adversariais.

Status: concluído no escopo local descrito.

Commits: nenhum; correções locais no branch atual.

Arquivos alterados nesta etapa: app/src/lib/http.ts,
app/src/lib/http-respostas.test.ts, app/src/lib/error-capture.ts,
app/src/lib/error-capture.test.ts e este relatório.

Testes: app 244 passaram / 2 pulados; tsc, ESLint e build ok; auditoria e
conciliação do banco ok. Backend não alterado nem repetido nesta etapa.

O que NÃO foi feito e por quê: implantação/testes na Azure, carga prolongada,
integrações reais e garantia absoluta de segurança, por não fazerem parte da
validação local disponível. Nenhum commit ou push foi solicitado.

Problemas que vi fora do escopo: permanecem as pendências de produção dos
relatórios anteriores. Nenhuma falha confirmada nesta etapa ficou sem correção.

Como testar na mão:

1. Em app, executar npx vitest run src/lib/http-respostas.test.ts
   src/lib/sessao.test.ts src/lib/error-capture.test.ts.
2. Conferir nos casos simulados que trocar a conta durante refresh não gera
   outra chamada de pagamento, que respostas antigas são descartadas e que o
   logout mantém sua chamada de revogação.
3. Abrir http://127.0.0.1:8081/ para usar o app local.
