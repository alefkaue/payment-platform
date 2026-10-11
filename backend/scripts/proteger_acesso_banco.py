"""Protege um banco EXISTENTE sem recriar papéis ou trocar senhas.
DATABASE_ADMIN_URL deve pertencer ao administrador do banco. Aplicar somente no
banco dedicado ao Astro, após backup. Depois, rodar restringir_runtime.py como migrador.
"""
import os
from sqlalchemy import create_engine, text


def proteger(connection):
    q = connection.dialect.identifier_preparer.quote
    banco = q(connection.scalar(text('SELECT current_database()')))
    connection.execute(text(f'REVOKE ALL ON DATABASE {banco} FROM PUBLIC, astro_app'))
    connection.execute(text(f'GRANT CONNECT ON DATABASE {banco} TO astro_app, astro_migrator'))
    connection.execute(text('REVOKE ALL ON SCHEMA public FROM PUBLIC, astro_app'))
    connection.execute(text('GRANT USAGE ON SCHEMA public TO astro_app'))
    connection.execute(text('GRANT USAGE, CREATE ON SCHEMA public TO astro_migrator'))
    elevados = connection.scalar(text("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname = 'astro_app'"))
    if elevados is None or elevados:
        raise RuntimeError('astro_app ausente ou com atributos administrativos. Corrija com o administrador antes de prosseguir.')
    connection.execute(text('ALTER ROLE astro_app NOINHERIT CONNECTION LIMIT 30'))
    connection.execute(text('ALTER ROLE astro_app SET search_path = pg_catalog, public'))
    for opcao, valor in [('statement_timeout', '15s'), ('lock_timeout', '5s'), ('idle_in_transaction_session_timeout', '30s')]:
        connection.execute(text(f"ALTER ROLE astro_app SET {opcao} = '{valor}'"))
    # Membership dá acesso via SET ROLE mesmo com NOINHERIT: falha e exige revisão.
    membros = connection.scalar(text("SELECT count(*) FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = 'astro_app')"))
    if membros:
        raise RuntimeError('astro_app participa de outros papéis. Revise e revogue as associações antes de prosseguir.')
    connection.execute(text('ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator IN SCHEMA public REVOKE ALL ON TABLES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator IN SCHEMA public REVOKE ALL ON SEQUENCES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES FOR ROLE astro_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC'))


if __name__ == '__main__':
    engine = create_engine(os.environ['DATABASE_ADMIN_URL'], hide_parameters=True)
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Este script requer PostgreSQL.')
    with engine.begin() as connection:
        proteger(connection)
    print('Acesso administrativo e privilégios padrão conferidos; dados preservados.')
