# Imagem do BANCO: Postgres oficial + o script que cria os papéis de privilégio
# mínimo (astro_app / astro_migrator) na PRIMEIRA inicialização do volume.
#
# Não contém segredo: as senhas chegam por variável de ambiente em runtime
# (POSTGRES_PASSWORD, DATABASE_APP_PASSWORD, DATABASE_MIGRATION_PASSWORD) — ver
# docker-compose.yml. Rode sempre com POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256.
FROM postgres:16-alpine

# Scripts em /docker-entrypoint-initdb.d/ rodam só quando o volume é criado.
COPY init-roles.sh /docker-entrypoint-initdb.d/10-roles.sh
RUN chmod 0555 /docker-entrypoint-initdb.d/10-roles.sh
