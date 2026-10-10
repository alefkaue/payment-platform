"""
Engine e sessão do SQLAlchemy.

v6 -- unificação do repositório: existe UMA só implementação de repositório
(repositories/repository.py, sobre SQLAlchemy). O que muda entre ambientes é só a
engine:

- DATABASE_URL definida  -> Postgres (produção / Docker / Azure).
- DATABASE_URL ausente    -> SQLite num arquivo local (`payflow.db`), para
  desenvolvimento rápido sem subir Postgres. O MESMO ORM e a MESMA lógica de
  repositório rodam nos dois -- antes havia um repositório em memória (dict)
  paralelo que precisava reimplementar tudo à mão e divergia na prática.
- DATABASE_URL = "sqlite://" (in-memory) -> usado pelos testes (ver tests/).

A DATABASE_URL vem de core/config.py, que carrega o `.env` automaticamente
(bug #7 da auditoria -- não precisa mais de `source .env`).

Nota de concorrência: o SELECT ... FOR UPDATE que fecha a condição de corrida da
transferência só é efetivo no Postgres. No SQLite (dev) ele é ignorado, mas o
SQLite serializa escritas com lock de banco, o que é suficiente para o uso
single-process de desenvolvimento. Produção é Postgres.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _url_efetiva() -> str:
    return get_settings().database_url or "sqlite:///./payflow.db"


def _criar_engine():
    url = _url_efetiva()
    if url.startswith("sqlite"):
        # check_same_thread=False: FastAPI atende requisições em threads diferentes.
        connect_args = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # In-memory (testes): StaticPool mantém a MESMA conexão, senão cada
            # conexão veria um banco vazio diferente.
            return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
        return create_engine(url, connect_args=connect_args)
    # pool_pre_ping evita erro de "conexão caiu" após ociosidade (VM que hiberna,
    # banco gerenciado que recicla conexões).
    return create_engine(url, pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 10})


engine = _criar_engine()
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _integridade_sqlite(conexao, _registro):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def usando_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def criar_tabelas() -> None:
    """Cria as tabelas que ainda não existem. Em produção, migrações versionadas
    ficam no Alembic (ver backend/alembic/)."""
    from app.db import models  # noqa: F401 -- registra os modelos no Base

    Base.metadata.create_all(bind=engine)


def conferir_runtime_producao() -> None:
    """A API de produção não pode ser superusuário nem dona das tabelas."""
    with engine.connect() as connection:
        privilegiado = connection.scalar(text("""
            SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls
            FROM pg_roles WHERE rolname = current_user
        """))
        dono = connection.scalar(text("""
            SELECT count(*) FROM pg_tables
            WHERE schemaname = 'public' AND tableowner = current_user
        """))
        ddl = connection.scalar(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')"))
        if privilegiado or dono or ddl:
            raise RuntimeError("Credencial da API tem privilégios excessivos; use astro_app.")


def banco_disponivel() -> bool:
    try:
        with engine.connect() as connection:
            return connection.scalar(text("SELECT 1")) == 1
    except Exception:
        return False
