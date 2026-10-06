"""
Ponto único de obtenção do repositório. v6: existe uma só implementação
(repository.Repositorio, sobre SQLAlchemy) -- Postgres em produção, SQLite em
dev/testes, escolhido pela engine em app/db/base.py. Não há mais repositório em
memória paralelo.
"""

from functools import lru_cache

from app.db.base import SessionLocal, criar_tabelas
from app.repositories.repository import Repositorio


@lru_cache
def get_repository() -> Repositorio:
    criar_tabelas()
    return Repositorio(SessionLocal)
