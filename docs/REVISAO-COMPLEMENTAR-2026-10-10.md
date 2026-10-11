# Revisão complementar do banco, API e site — 10/10/2026

Revisão adicional sobre as correções descritas em PENTEST-2026-10-10.md,
REVISAO-SEGURANCA-BANCO-2026-10-10.md e REVISAO-PERIMETRO-2026-10-10.md.
Os testes financeiros usam dados fictícios em banco separado. No banco do app,
esta revisão executou apenas auditoria de permissões e conciliação de leitura.

## Problemas confirmados e corrigidos nesta etapa

1. O cliente HTTP lançava SyntaxError ao receber HTML ou JSON corrompido da API.
   Agora retorna ApiError com mensagem controlada. Uma leitura interrompida ou
   resposta inválida de sucesso orienta conferir o resultado antes de repetir a
   operação; o cliente não reenvia pagamentos automaticamente nesses casos.
   Respostas vazias 204 continuam funcionando.
2. Uma renovação com HTTP 200 e tokens ausentes, vazios ou de tipo inválido
   substituía a sessão válida. A resposta agora é validada antes de salvar tokens.
   Uma resposta inválida preserva a sessão local e não reenvia a operação.
   Um 401 com corpo HTML também encerra corretamente a sessão quando a renovação
   foi recusada.
3. O gerador de CSP podia escolher .env.local antes de .env.production, ignorar
   expansão de variáveis e substituir um valor vazio definido pelo processo.
   Agora usa loadEnv do próprio Vite, alinhando a origem autorizada à usada pelo
   build. [Regras oficiais de precedência e expansão](https://vite.dev/guide/env-and-mode).
4. A captura de objetos Error do servidor expandia mensagem, pilha e causas
   também em produção, com risco de registrar dados sensíveis. Em produção,
   essa descrição passa a ser genérica; desenvolvimento conserva diagnóstico.

Os quatro comportamentos acima foram tratados em três grupos de correções:
cliente HTTP/sessão, configuração de CSP e registro de exceções.

## Evidências

- Backend completo: 546 passaram, 43 pulados; um aviso de depreciação do TestClient.
- PostgreSQL financeiro: 96 passaram, 1 pulado por contrato de chave por item.
  Inclui concorrência, idempotência, limites financeiros, devoluções, folha,
  split, outbox e recuperação de pendências.
- Migrações e permissões com credencial restrita: 28 passaram. Upgrade,
  downgrade, novo upgrade e alembic check passaram em banco isolado.
- Site: 235 passaram, 2 pulados, incluindo 17 regressões novas nesta etapa.
- TypeScript e ESLint dos arquivos alterados: sem erros. git diff --check passou.
- Build de produção passou com VITE_API_URL=https://api.astro.test, endereço
  fictício de teste. Origem de conexão e hashes dos três scripts inline conferidos
  no artefato; nenhum dos segredos locais conhecidos procurados foi encontrado
  no pacote cliente. A busca não substitui uma auditoria completa de segredos.
- Auditoria do banco do app: nenhum desvio da política de privilégios.
- Conciliação do banco do app: zero históricos sem transação, saldos negativos
  indevidos, transações desbalanceadas ou carteiras divergentes do histórico.
- Site local e readiness da API responderam HTTP 200 ao final.

O computador reiniciou durante os testes. O PostgreSQL recuperou seu WAL;
site, API, auditoria e conciliação foram verificados novamente. A suíte financeira
interrompida foi repetida integralmente depois de o banco aceitar conexões.

## Limites desta revisão

Não houve implantação nem teste contra Azure, WAF, domínio público ou integrações
financeiras reais. A instalação local continua em desenvolvimento, incluindo
configurações de demonstração; ela não comprova adequação à produção.
Não foram realizados ensaios completos de câmera/aparelhos reais, carga prolongada
ou falhas distribuídas. As verificações reduzem riscos nos cenários cobertos e não
estabelecem ausência absoluta de vulnerabilidades. Não houve commit ou push.

## Resultado

Cartão: revisão complementar de erros e vulnerabilidades solicitada pelo usuário.

Status: concluído no escopo local descrito acima.

Commits: nenhum; alterações disponíveis no branch atual.

Arquivos alterados nesta etapa: app/src/lib/http.ts,
app/src/lib/http-respostas.test.ts, app/scripts/cabecalhos.mjs,
app/scripts/cabecalhos.d.mts, app/src/lib/cabecalhos-ambiente.test.ts,
app/src/lib/error-capture.ts, app/src/lib/error-capture.test.ts e este relatório.
As alterações anteriores do banco e da API foram preservadas.

Testes: backend 546 passaram / 43 pulados; PostgreSQL 96 passaram / 1 pulado;
permissões e migrações 28 passaram; app 235 passaram / 2 pulados; tsc ok;
ESLint dos arquivos alterados ok; build ok.

O que NÃO foi feito e por quê: validação da infraestrutura definitiva, integrações
reais, testes de aparelhos e garantia de segurança absoluta, conforme os limites
descritos acima. Nenhuma publicação foi solicitada nesta etapa.

Problemas que vi fora do escopo: permanecem as pendências de produção documentadas
nos relatórios anteriores; nenhuma falha adicional confirmada ficou sem correção
nesta etapa.

Como testar na mão:

1. Abrir http://127.0.0.1:8081/; a API local usa http://127.0.0.1:8765.
2. Em app, executar npx vitest run src/lib/http-respostas.test.ts
   src/lib/cabecalhos-ambiente.test.ts src/lib/error-capture.test.ts para reproduzir
   as novas regressões com respostas e tokens fictícios.
3. Usar scripts/auditar_runtime.py e scripts/verificar_banco.py no backend com
   a configuração local da API para conferir permissões e conciliação sem alterar
   registros. Não executar fixtures pytest contra o banco de clientes.
