## Resultado

Cartão: concluir as etapas 1–5 de cifragem, isolamento, validação, migração local e preparação do Docker.

Status: concluído no escopo descrito abaixo. Isso não significa ausência de vulnerabilidades nem isolamento integral de todo o ledger.

Commits: nenhum nesta etapa; alterações no worktree atual, sem push, merge ou mudança de branch.

Arquivos alterados nesta etapa:

- `.env.example`, `.env.docker.example`, `docker-compose.yml`, `.github/workflows/backend.yml`.
- `README.md`, `AZURE.md`, `docs/BANCO.md`, `docs/INVENTARIO-RISCOS-2026-10-10.md` e este relatório.
- `infra/postgres/init-roles.sh`, `infra/azure/main.bicep`.
- `backend/alembic/env.py` e novas versões `f01d892ca740_dados_pessoais.py`, `f21d04aca891_isolamento_titulares.py`, `f31a15bd9022_documento_duplicado_isolado.py`.
- `backend/app/core/config.py`, `backend/app/core/dados_pessoais.py`.
- `backend/app/db/base.py`, `models.py`, `dados_cifrados.py`, `isolamento.py`, `permissoes.py`, `seguranca_runtime.py`.
- `backend/app/main.py`, `backend/app/deps.py`, `backend/app/services/auth_service.py`.
- `backend/app/repositories/repository.py`, `backend/app/repositories/extras.py`.
- `backend/scripts/proteger_acesso_banco.py`, `restringir_runtime.py`, `cifrar_dados_pessoais.py`, `configurar_isolamento.py`.
- `backend/tests/conftest.py`, `test_config_producao.py`, `test_cadastro_identidade.py`, `test_acesso_runtime_postgres.py`, `test_dados_cifrados.py`, `test_isolamento_titulares.py`.

As alterações de segurança anteriores continuam no worktree. Arquivos privados `.env`/`.env.docker`, chaves, backups e ferramentas de conferência não são versionados e não contêm dados reproduzidos neste relatório.

### O que foi concluído

1. **Migração:** corrigida a criação do esquema privado. O administrador provisiona `astro_privado` para o migrador; a API não recebe permissão de criar esquemas. Corrigida a preservação dos índices compostos/condicionais usados no controle de uso único. `alembic check` passou em bancos migrados com dono migrador e com dono administrativo.
2. **Isolamento:** dispositivos, refresh tokens, desafios, documentos PF/PJ, funcionários, cartões e limites têm RLS com FORCE. O contexto assinado fica preso à conexão, transação e prazo. Prova adulterada, expirada ou reutilizada não autoriza acesso. Usuários/vínculos têm proteção adicional de escrita contra criação de administradores e vínculos indevidos por credencial SQL sem contexto. Revogar vínculo corta a leitura dos objetos internos PJ. O cadastro lê apenas documentos do caso criado no seu contexto; uma função restrita devolve só existência de documento duplicado, preservando o controle sem revelar campos. A auditoria recusa runtime dono da função de contexto.
3. **Cifragem:** dados cadastrais e conteúdos sensíveis definidos em `CAMPOS` usam Fernet autenticado com contexto da coluna. Igualdade e unicidade usam índices HMAC com chave independente. Cadastro, login, Pix fictício, replay, recuperação, JSON/datas e rotação foram conferidos. Uma falha na rotação de banco criado pela fixture PostgreSQL foi corrigida: o script só suspende o gatilho de auditoria quando ele existe. Em banco migrado ele é reativado antes do commit; erro reverte inclusive o DDL.
4. **Banco local:** `astro_demo`, PostgreSQL em Docker acessível localmente em `127.0.0.1:55432`, foi atualizado até `f31a15bd9022`. A API foi parada antes do backup final e da migração. Contagens e valores normalizados de **32 tabelas** foram comparados antes/depois, incluindo os bytes da biometria, sem divergências. Backup cifrado foi restaurado em banco descartável. Rotação preservou os valores; adulteração provocou rollback. Runtime, constraints validadas, auditoria e conciliação financeira foram aprovados. A API foi reiniciada e o login administrativo com DPoP, consulta da sessão e logout funcionaram.
5. **Docker/configuração/documentação:** chaves independentes e persistentes provisionadas em arquivos privados com modo 600; defaults de DPoP/hosts do Compose separados da API nativa. Bootstrap, job migrador, conversão dos dados, configuração do contexto e ACLs estão na ordem necessária. YAML, shell do bootstrap, compilação Python, `docker compose --env-file .env.docker config --quiet` e `git diff --check` passaram. Documentados backup, restauração, rotação, limites da proteção e uso de dados fictícios.

### Testes

- Suíte completa SQLite: **649 passaram / 55 pulados**, sem falhas, antes de acrescentar a última regressão de propriedade da função (exclusiva do banco migrado).
- Dos 55 pulados nessa execução, 38 exigiam banco PostgreSQL migrado/runtime restrito, 16 exigiam recursos do PostgreSQL e 1 era uma combinação fora do contrato de lote (chave global; o lote usa chave por item). Pular não equivale a passar.
- Suíte completa PostgreSQL: **664 passaram / 36 pulados / 1 falhou**. A falha era no teste de rotação com tabelas criadas pela fixture, sem gatilho de auditoria. Corrigido o script; rechecagem dos **6 testes de cifragem no PostgreSQL passou**. A suíte inteira PostgreSQL não foi repetida após essa correção; não se apresenta a primeira execução como totalmente aprovada.
- Banco PostgreSQL migrado, credencial restrita: **39 passaram**, incluindo a última regressão de propriedade da função. A configuração com dono administrativo usada em CI passou 38 testes antes de acrescentar esse último cenário.
- Backup/restauração, comparação das 32 tabelas, rotação, adulteração com rollback, Alembic e conferências locais: aprovados em bancos descartáveis e no banco local conforme descrito.
- Frontend não recebeu alterações nesta etapa; testes/tsc não foram repetidos. A validação anterior registrava 258 testes aprovados e 2 pulados.

### O que NÃO foi feito e por quê

- Nenhum deploy, criação de recurso Azure, publicação GitHub ou início de uma nova instalação Compose. Esta etapa prepara o Docker; a API nativa local e o PostgreSQL Docker existente continuam funcionando.
- O Bicep recebeu referências às novas chaves, mas não foi compilado nem aplicado: CLI Azure/Bicep indisponível e implantação fora desta etapa.
- Carteiras e ledger não têm RLS integral. Conservam autorização da API, privilégios financeiros e controles de integridade. As políticas novas não eliminam o impacto de SQL injection ou comprometimento da API nas tabelas ainda compartilhadas.
- A cifragem vincula a coluna, não o id da linha. Índices revelam igualdade no mesmo domínio; metadados e valores financeiros não são todos cifrados. Administradores e tarefas internas assinadas mantêm acesso amplo.
- Cofre externo definitivo, criptografia física do volume, retenção externa, rotação automática e RPO/RTO operacional permanecem para a configuração da infraestrutura. Chaves acessíveis ao host não protegem contra comprometimento completo desse host.
- Nenhum requisito de CPF/RG pertencente a pessoa real foi acrescentado. Pix/documentos continuam simulação; formato/dígitos verificadores não comprovam identidade real.

### Problemas que vi fora do escopo

`Repositorio.desativar_vinculo` ainda altera apenas `ativo`, sem atualizar `status`, embora o contrato do banco exija coerência entre ambos. O fluxo principal de equipe usa os métodos que atualizam os dois campos. Esse método legado não foi alterado aqui; deve ser revisado no cartão de equipe.

### Como testar na mão

1. Abra o site local em `http://localhost:8081`; a API nativa continua em `http://127.0.0.1:8765`. `/saude` e `/pronto` respondem 200.
2. Use dados fictícios, cadastre duas contas e confira login/Pix simulado. Nenhuma transferência liquida perante banco real.
3. Com a credencial runtime e as chaves privadas, execute `scripts/auditar_runtime.py` e `scripts/verificar_banco.py`; ambos devem aprovar.
4. Em banco descartável migrado, configure `TEST_RUNTIME_DATABASE_URL` e `TEST_ADMIN_DATABASE_URL` e execute os testes de acesso, migrações e isolamento. Nunca aponte a fixture de testes destrutiva para `astro_demo`.
5. Quando for usar Compose, execute `docker compose --env-file .env.docker up --build`; configure o app para `VITE_API_URL=http://127.0.0.1:8000`, igual à origem DPoP do Docker. Para volume existente, siga a parada/backup/migração documentada em `docs/BANCO.md`.
