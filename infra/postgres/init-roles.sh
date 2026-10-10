#!/bin/sh
# Só roda na criação de um volume NOVO. Volume existente: seguir docs/BANCO.md.
set -eu
: "${DATABASE_APP_PASSWORD:?defina DATABASE_APP_PASSWORD}"
: "${DATABASE_MIGRATION_PASSWORD:?defina DATABASE_MIGRATION_PASSWORD}"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 \
  --set app_password="$DATABASE_APP_PASSWORD" --set migration_password="$DATABASE_MIGRATION_PASSWORD" <<'SQL'
SET password_encryption = 'scram-sha-256';
CREATE ROLE astro_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE astro_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO astro_app, astro_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO astro_migrator;
GRANT USAGE ON SCHEMA public TO astro_app;
ALTER ROLE astro_app SET search_path = public;
ALTER ROLE astro_app SET statement_timeout = '15s';
ALTER ROLE astro_app SET lock_timeout = '5s';
ALTER ROLE astro_app SET idle_in_transaction_session_timeout = '30s';
ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO astro_app;
ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO astro_app;
ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
