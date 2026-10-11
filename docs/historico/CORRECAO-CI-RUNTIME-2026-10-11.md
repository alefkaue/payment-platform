## Resultado

Cartão: corrigir falha em “Credencial runtime e trilha imutável no banco migrado”.
Status: correção validada localmente; nova execução remota acionada pelo push.
Commits: commit desta correção, publicado após a validação.
Arquivos alterados: backend/tests/test_acesso_runtime_postgres.py e este relatório.
Testes: 41 passaram na ordem exata do workflow, com funções pertencentes ao administrador como no CI; outros 41 passaram com funções pertencentes ao migrador como no Docker. Alembic check e git diff --check aprovados. Falha original reproduzida antes da correção em banco descartável.
O que NÃO foi feito e por quê: nenhuma alteração da API, migração ou permissões dos bancos em uso; nenhuma implantação Azure. A conclusão da nova execução completa no GitHub deve ser consultada no Actions.
Problemas que vi fora do escopo: não identificados nesta correção.
Como testar na mão: executar tests/test_migracoes_privilegios.py, tests/test_acesso_runtime_postgres.py e tests/test_isolamento_titulares.py nessa ordem em banco PostgreSQL descartável migrado, com TEST_ADMIN_DATABASE_URL e TEST_RUNTIME_DATABASE_URL. Conferir a nova execução Backend no GitHub Actions.

A execução 38171413625 passou nos testes SQLite, na suíte PostgreSQL completa e nas migrações. A etapa runtime teve erros de permission denied for function astro_contexto nos testes posteriores ao teste que simula propriedade indevida da função pela API.

O teste restaurava o proprietário original da função, mas ALTER OWNER podia remover o GRANT EXECUTE explícito que astro_app possuía. A correção registra a permissão anterior e a restaura junto com o proprietário no finally. Ao terminar, o próprio teste verifica a política de privilégio mínimo e a execução da função sem prova (retorno NULL). A API continua sem propriedade das funções e sem acesso administrativo. Não foram removidos testes nem afrouxadas as restrições operacionais.
