"""
Engine e sessão do SQLAlchemy. Configurado 100% via variável de ambiente
DATABASE_URL -- não tem nada hardcoded aqui de propósito (mentalidade de nuvem:
localmente aponta pro Postgres do Ubuntu Server, em produção aponta pro Azure
Database for PostgreSQL só trocando a env var, sem tocar em código).

Formato esperado (driver psycopg2, síncrono -- combina com as rotas da API,
que já são `def` síncronas por causa do DeepFace ser CPU-bound):
    postgresql+psycopg2://usuario:senha@host:5432/nome_do_banco
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _criar_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    # pool_pre_ping evita erro de "conexão caiu" depois de um tempo ocioso
    # (comum em VM que hiberna ou em banco gerenciado que recicla conexões).
    return create_engine(database_url, pool_pre_ping=True)


engine = _criar_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False) if engine else None


def postgres_disponivel() -> bool:
    """True se DATABASE_URL estiver configurada -- é isso que decide, em
    repositories/__init__.py, se a API usa Postgres ou o repositório em
    memória (não muda nenhuma outra parte do código)."""
    return engine is not None


def criar_tabelas() -> None:
    """Cria as tabelas que ainda não existem (CREATE TABLE IF NOT EXISTS,
    efetivamente). Para um MVP em desenvolvimento isso é suficiente; quando o
    schema já tiver dados de verdade em produção, trocar por Alembic
    (não incluído aqui de propósito -- ver README) para migrações versionadas
    em vez de recriar o schema inteiro."""
    from app.db import models  # noqa: F401 -- garante que os modelos foram registrados no Base

    Base.metadata.create_all(bind=engine)
