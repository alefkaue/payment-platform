## Resultado

Cartão: isolamento financeiro, interface de pagamentos, reenvios e correção de vínculo.
Status: concluído no escopo descrito abaixo.
Commits: nenhum nesta etapa; alterações anteriores preservadas na branch atual, sem push.

Arquivos alterados nesta etapa:

- `backend/alembic/versions/f41b26ce0133_isolamento_financeiro.py`
- `backend/app/db/isolamento.py`, `permissoes.py`, `seguranca_runtime.py`
- `backend/app/deps.py`
- `backend/app/repositories/repository.py`, `extras.py`
- `backend/app/routers/pagamentos.py`
- `backend/app/services/pix_service.py`, `pagamento_service.py`, `folha_service.py`, `beneficios_service.py`
- `backend/scripts/verificar_banco.py`
- `backend/tests/test_isolamento_titulares.py`, `test_acesso_runtime_postgres.py`, `test_migracoes_privilegios.py`, `test_auditoria_atomica.py`, `test_deposito_idempotencia.py`
- `app/src/lib/api.ts`, `types.ts`
- `app/src/routes/_app.depositar.tsx`, `_app.transferir.tsx`
- `app/src/test/deposito-fluxo.test.tsx`
- `docs/BANCO.md` e este relatório.

Testes:

- Backend completo, SQLite: **654 passaram / 58 pulados**. Os pulados exigem PostgreSQL/credencial migrada, exceto o contrato de cabeçalho global de lote que não se aplica à rota.
- PostgreSQL descartável, Alembic e credencial runtime restrita: **41 passaram**, sem testes pulados. Inclui migração, privilégios, isolamento, API integrada, folha, estorno, reenvio concorrente e saldo insuficiente sob concorrência.
- Interface completa: **263 passaram / 2 pulados**.
- TypeScript, ESLint dos arquivos alterados e `git diff --check`: aprovados.
- `alembic check`: aprovado nas bases isolada, restaurada e local atualizada.
- Backup cifrado restaurado em base descartável: valores e contagens das **32 tabelas** preservados; adulteração e rotação de cifragem verificadas.
- Aplicação local: backup final cifrado, atualização para `f41b26ce0133`, comparação dos valores das 32 tabelas, auditoria imutável, permissões e conciliação aprovadas; API reiniciada.
- Docker: imagem do backend construída; Compose iniciou PostgreSQL e API; job de migração terminou com código 0. API `/saude` e `/pronto` responderam 200. Conferência de privilégio mínimo/isolamento e conciliação executadas dentro do container.
- Container: UID 10001, sistema de arquivos somente leitura, capacidades removidas e `no-new-privileges`; PostgreSQL sem porta publicada.

O que foi corrigido:

1. `FORCE RLS` em carteiras, transações e histórico de saldo, somado às dez tabelas já protegidas. Uma credencial SQL sem prova não lê saldos nem extratos. Um titular não lê a carteira nem o depósito de outro titular.
2. Consulta de destinatário separada dos dados financeiros. Pix, comprovantes, cobrança, catálogo e folha usam identificação de conta sem saldo. Movimentação libera somente as carteiras da operação na sessão SQL, após validar a carteira que autoriza o débito. O contexto não passa para uma nova sessão ou conexão do pool.
3. Locks financeiros usam o dialect da sessão efetivamente aberta; um repositório PostgreSQL não perde locks por a configuração global apontar para SQLite. Testado com solicitações concorrentes usando RLS real.
4. Depósito fictício aceita chave idempotente por conta e operação. Reenvio devolve a mesma transação; alterar o valor com a mesma chave responde 409. Cabeçalho e corpo conflitantes são recusados.
5. Interface bloqueia envio simultâneo, mantém a chave após erro de rede, impede editar o valor em envio e limpa o depósito ao trocar de conta. Respostas atrasadas de telas desmontadas e temporizadores anteriores não redirecionam a nova conta.
6. `desativar_vinculo` agora atualiza `ativo`, `status='revogado'` e `status_em`, com auditoria na mesma transação. Falha de auditoria reverte a alteração.
7. Conciliação global recusa contexto ausente ou filtrado, para não declarar integridade com base em uma leitura vazia por RLS.

O que NÃO foi feito e por quê:

- Nenhum deploy Azure: proibição expressa do usuário mantida.
- Nenhum push/commit: não solicitado nesta etapa; instruções da worktree também proíbem push.
- Frontend não ganhou imagem Docker: segue no Vite local. O Compose validado contém backend, PostgreSQL e job de migração.
- Não foi repetida a suíte PostgreSQL inteira sobre schema criado por fixtures; foi executada a suíte específica do schema migrado, com privilégio mínimo e concorrência real, além de toda a suíte SQLite.
- Não foi realizado teste humano com câmera física nesta etapa; os testes da interface incluem os testes automatizados existentes de cadastro, câmera, recuperação e sessão.
- Sem garantia de ausência absoluta de vulnerabilidades.

Problemas que vi fora do escopo / limites restantes:

- Usuários e vínculos mantêm leitura de envelopes cifrados para autenticação/convites; outras tabelas financeiras, como cobranças e pendências, continuam combinando autorização por objeto na API e ACLs. Esta etapa protege especificamente os saldos, transações e histórico financeiro.
- Comprometer o processo da API e suas chaves ainda permite forjar contexto operacional. A separação entre migração/API e RLS não substitui proteção do ambiente.
- A intenção de pagamento do cliente dura enquanto a tela permanece montada. Fechar/reabrir a tela perde essa chave; um novo pagamento recebe outra intenção. Clientes antigos que omitem a chave de depósito não têm garantia de reenvio idempotente.
- O Compose usa banco novo, separado da base local com os dados existentes. Os dados anteriores não foram copiados para esse novo volume; o app existente continua integrado à base local atualizada.

Como testar na mão:

1. Abrir `http://localhost:8081`: frontend atual, integrado à API `http://127.0.0.1:8765`, com os dados existentes preservados.
2. Em Transferir, revisar destinatário/valor, confirmar e conferir comprovante e saldos nas duas contas. Após erro de rede, tentar novamente na mesma tela.
3. Em Depositar, digitar o valor e enviar. Durante o envio, campo e atalhos ficam bloqueados. Trocar a conta limpa valor/erro; a resposta atrasada não abre o comprovante ou redireciona a conta nova.
4. Na API, repetir `/pagamentos/depositar-demo` com a mesma chave/valor: mesmo id e um crédito. Trocar valor com a mesma chave: 409. Reutilizar a chave em outra conta: intenção separada.
5. Para Docker, executar `docker compose --env-file .env.docker ps -a`; banco deve estar saudável, backend executando e migração encerrada com 0. A API Docker está em `http://127.0.0.1:8000`.
6. Consultar `/saude` e `/pronto` nas APIs local e Docker. Para conciliação Docker: `docker compose --env-file .env.docker exec -T backend python scripts/verificar_banco.py`.
