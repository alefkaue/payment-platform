"""
Ponto único de decisão: se DATABASE_URL está configurada, usa Postgres; senão,
cai pro repositório em memória (fica fácil rodar localmente sem precisar subir
um Postgres pra um teste rápido). Routers e services só importam
`get_repository` -- nunca uma classe de repositório específica.
"""

from functools import lru_cache
from typing import Protocol

from app.db.base import SessionLocal, criar_tabelas, postgres_disponivel
from app.repositories.memoria_repository import MemoriaRepository


class Repositorio(Protocol):
    """Documenta o contrato que qualquer repositório precisa cumprir. Não é
    obrigatório herdar disso -- MemoriaRepository e PostgresRepository só
    precisam ter os mesmos métodos (duck typing), isso aqui é só pra deixar
    claro, lendo o arquivo, o que um repositório novo (ex: Cosmos DB) precisa
    implementar."""

    def carteira_existe(self, carteira_id: int) -> bool: ...
    def criar_usuario(self, carteira_id: int, nome: str, saldo_inicial: float = 0.0) -> dict: ...
    def obter_usuario(self, carteira_id: int) -> dict | None: ...
    def listar_usuarios(self) -> list[dict]: ...
    def atualizar_saldo(self, carteira_id: int, novo_saldo: float) -> None: ...
    def salvar_embedding_facial(self, carteira_id: int, embedding: list[float]) -> None: ...
    def obter_embedding_facial(self, carteira_id: int) -> list[float] | None: ...
    def executar_transferencia(
        self, origem_carteira_id: int, destino_carteira_id: int, valor: float, verificacao_facial: dict
    ) -> dict: ...
    def listar_transacoes(self) -> list[dict]: ...


@lru_cache
def get_repository() -> Repositorio:
    if postgres_disponivel():
        # import tardio pra não exigir sqlalchemy/psycopg2 instalados em quem
        # só quiser rodar em memória sem Postgres.
        from app.repositories.postgres_repository import PostgresRepository

        criar_tabelas()
        return PostgresRepository(SessionLocal)
    return MemoriaRepository()
