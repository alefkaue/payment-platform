"""Após alembic upgrade, restringe a API a DML e torna trilhas append-only.
Executar usando DATABASE_MIGRATION_URL, nunca com a credencial de runtime.
"""
import os
from sqlalchemy import create_engine, text


def restringir(connection):
    connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO astro_app"))
    connection.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO astro_app"))
    connection.execute(text("REVOKE ALL ON public.alembic_version FROM astro_app"))
    connection.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON public.historico_saldo, public.logs_auditoria FROM astro_app"))
    # A transação original só muda de estado: valores, titulares e autor são imutáveis para a API.
    connection.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON public.transacoes FROM astro_app"))
    connection.execute(text("GRANT UPDATE (status, bloqueio_ate) ON public.transacoes TO astro_app"))


if __name__ == "__main__":
    url = os.environ["DATABASE_MIGRATION_URL"]
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Este script requer PostgreSQL.")
    with engine.begin() as connection:
        restringir(connection)
