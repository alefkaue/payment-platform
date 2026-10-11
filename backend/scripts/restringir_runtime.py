"""Reaplica a lista explícita de permissões, sem alterar registros.
Executar após Alembic com DATABASE_MIGRATION_URL (dono dos objetos).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, inspect, text
from app.db.permissoes import TABELAS_RUNTIME, COLUNAS_UPDATE, privilegios_tabela


def restringir(connection):
    existentes = set(inspect(connection).get_table_names(schema='public'))
    if not TABELAS_RUNTIME <= existentes:
        raise RuntimeError('Aplique todas as migrações antes de restringir runtime.')
    # Remove inclusive grant options, referências e permissões anteriores em colunas.
    connection.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, astro_app'))
    connection.execute(text('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, astro_app'))
    connection.execute(text('REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM PUBLIC, astro_app'))
    preparador = connection.dialect.identifier_preparer
    objetos = existentes | set(inspect(connection).get_view_names(schema='public')) | set(inspect(connection).get_materialized_view_names(schema='public'))
    for nome in sorted(objetos):
        colunas = inspect(connection).get_columns(nome, schema='public')
        lista = ', '.join(preparador.quote(c['name']) for c in colunas)
        tabela = 'public.' + preparador.quote(nome)
        for privilegio in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES'):
            connection.execute(text(f'REVOKE {privilegio} ({lista}) ON {tabela} FROM PUBLIC, astro_app'))
    for nome in sorted(TABELAS_RUNTIME):
        lista = ', '.join(privilegios_tabela(nome))
        connection.execute(text(f'GRANT {lista} ON public.{preparador.quote(nome)} TO astro_app'))
    for nome, colunas in sorted(COLUNAS_UPDATE.items()):
        lista = ', '.join(preparador.quote(c) for c in sorted(colunas))
        connection.execute(text(f'GRANT UPDATE ({lista}) ON public.{preparador.quote(nome)} TO astro_app'))
    # Somente sequências vinculadas às tabelas aprovadas; setval fica proibido.
    sequencias = connection.execute(text('''
        SELECT DISTINCT ns.nspname, seq.relname, t.relname AS tabela
        FROM pg_class seq JOIN pg_namespace ns ON ns.oid = seq.relnamespace
        JOIN pg_depend d ON d.objid = seq.oid AND d.classid = 'pg_class'::regclass
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace nt ON nt.oid = t.relnamespace
        WHERE seq.relkind = 'S' AND ns.nspname = 'public' AND nt.nspname = 'public'
          AND d.deptype IN ('a', 'i')
    '''))
    for schema, sequencia, tabela in sequencias:
        if tabela in TABELAS_RUNTIME:
            connection.execute(text(f'GRANT USAGE, SELECT ON SEQUENCE {preparador.quote(schema)}.{preparador.quote(sequencia)} TO astro_app'))
    # Novos objetos não ficam acessíveis até este script aprová-los.
    connection.execute(text('ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM astro_app, PUBLIC'))
    connection.execute(text('ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC'))


if __name__ == '__main__':
    engine = create_engine(os.environ['DATABASE_MIGRATION_URL'], hide_parameters=True)
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Este script requer PostgreSQL.')
    with engine.begin() as connection:
        restringir(connection)
