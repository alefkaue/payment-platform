"""Bootstrap privado do banco novo; executar apenas no job temporário Azure.

Não entrega credenciais administrativas à API. Não imprime DSNs ou senhas.
"""
import os
import subprocess
import sys

import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from proteger_acesso_banco import proteger


def executar():
    admin_url = os.environ["DATABASE_ADMIN_URL"]
    with psycopg2.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET password_encryption = 'scram-sha-256'")
            for role, variable in (("astro_migrator", "DATABASE_MIGRATION_PASSWORD"),
                                   ("astro_app", "DATABASE_APP_PASSWORD")):
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(os.environ[variable])))
            # Azure PG admin não é superuser: associação permite gerir objetos do migrador.
            cursor.execute("SELECT current_user")
            administrator = cursor.fetchone()[0]
            cursor.execute(sql.SQL("GRANT astro_migrator TO {} WITH ADMIN OPTION").format(sql.Identifier(administrator)))
    engine = create_engine(admin_url, hide_parameters=True)
    with engine.begin() as connection:
        proteger(connection)
    engine.dispose()
    # Subprocessos recebem apenas credenciais de migração e as chaves necessárias.
    environment = dict(os.environ)
    for variable in ("DATABASE_ADMIN_URL", "DATABASE_APP_PASSWORD", "DATABASE_MIGRATION_PASSWORD"):
        environment.pop(variable, None)
    for command in (
        ["alembic", "upgrade", "head"],
        [sys.executable, "scripts/configurar_isolamento.py"],
        [sys.executable, "scripts/restringir_runtime.py"],
        ["alembic", "check"],
    ):
        subprocess.run(command, env=environment, check=True)
    print("Bootstrap e migração concluídos; API usa papel limitado.", flush=True)


if __name__ == "__main__":
    try:
        executar()
    except Exception as error:
        print(f"Bootstrap falhou ({type(error).__name__}); valores de credenciais omitidos.", file=sys.stderr)
        sys.exit(1)
