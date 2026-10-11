# Revisão de segurança do banco — 10/10/2026

A política de acesso foi aplicada ao PostgreSQL local `astro_demo`. As 32 tabelas
mantiveram seus registros: contagens e hashes do conteúdo foram conferidos antes e
depois. A API e o app continuam conectados ao banco.

O papel da API recebe permissões explícitas por tabela e coluna. Ele não pode criar
objetos, assumir outro papel, alterar documento/papel de usuários ou titularidade de
carteiras, apagar registros financeiros nem modificar os registros definidos como
somente inclusão. Exclusões ficam restritas a chaves Pix e controles de replay DPoP.
Migrações usam outra identidade; novos objetos não recebem acesso automaticamente.

A auditoria verifica permissões efetivas, concessões a PUBLIC, associações de papéis,
sequências, funções e objetos desconhecidos. A inicialização de produção recusa uma
política divergente. Conexões e consultas têm limites; o Compose isola o banco numa
rede interna sem publicar sua porta. O banco local separado usa apenas loopback.

Os logs locais novos ocultam parâmetros SQL. Logs antigos e backups permanecem
restritos fora do Git. Foi restaurado um backup em banco isolado, reaplicada a
política e validada a integridade financeira. Nenhum teste destrutivo usou o banco
com os dados do app.

Não existe garantia de ausência de vulnerabilidades. Uma credencial da API roubada
ainda permite as operações autorizadas a esse papel; proteção da aplicação,
segredos, infraestrutura e monitoramento continua necessária. As identidades
administrativa e de migração têm poderes maiores. Esta revisão não provisionou
Azure nem criptografia física do disco local. A configuração operacional e os
comandos de auditoria estão em [BANCO.md](BANCO.md).

Referências: [privilégios PostgreSQL 16](https://www.postgresql.org/docs/16/ddl-priv.html)
e [associação de papéis](https://www.postgresql.org/docs/16/role-membership.html).

## Resultado

Cartão: endurecimento do banco solicitado pelo usuário.

Status: concluído no ambiente local.

Commits: nenhum novo commit ou push nesta tarefa.

Arquivos alterados:

- `backend/app/db/{base,permissoes,seguranca_runtime}.py`
- `backend/app/core/config.py`
- `backend/scripts/{restringir_runtime,proteger_acesso_banco,auditar_runtime}.py`
- `backend/tests/{test_politica_runtime,test_acesso_runtime_postgres}.py`
- `infra/postgres/init-roles.sh`, `docker-compose.yml`, `.env.example`
- `.github/workflows/backend.yml`, `docs/BANCO.md` e este relatório.

Testes:

- Backend completo: 492 passaram / 43 pulados.
- PostgreSQL financeiro e concorrência: 96 passaram / 1 pulado.
- PostgreSQL com papel restrito: 28 passaram, incluindo tentativas de acesso
  proibido e cadastro, login, depósito, Pix, devolução, cobrança e logout.
- Política unitária: 4 passaram. Migração upgrade/downgrade/upgrade e Alembic check
  passaram; não houve mudança de modelo que exigisse migração nova.
- Auditorias do banco local: nenhuma divergência de permissão ou integridade.
- Restauração do backup e validação do Compose passaram.
- App e TypeScript não foram alterados nesta tarefa; a revisão anterior teve
  218 testes do app passando / 2 pulados, TypeScript e build aprovados.

O que NÃO foi feito e por quê: publicação Git/Azure e provisionamento de serviços
externos ficam fora deste pedido. Não foram removidos dados, volumes ou logs antigos.

Problemas que vi fora do escopo: o ambiente local ainda usa configurações de
demonstração para algumas integrações e login biométrico legado. A atualização
anterior tornou a comparação documento/selfie informativa mesmo em produção;
essa decisão precisa de revisão antes de atender clientes reais.

Como testar na mão:

1. Abrir `http://127.0.0.1:8081` e acessar o fluxo de conta.
2. Conferir `http://127.0.0.1:8765/pronto`.
3. Com o ambiente da API carregado, executar no diretório `backend`
   `python scripts/auditar_runtime.py` e `python scripts/verificar_banco.py`.
4. Para adotar as restrições em outro ambiente, seguir a ordem administrativa,
   migração e auditoria documentada em `docs/BANCO.md`.
