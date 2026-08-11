"""
Repositório em memória (sem banco de dados).

A aplicação começa sempre com o repositório vazio. As contas/carteiras são
criadas exclusivamente pelo endpoint POST /usuarios.

A camada fica isolada para facilitar a futura substituição por Azure SQL
Database ou Azure Cosmos DB sem alterar as regras de negócio.
"""

from itertools import count
from typing import Optional


class MemoriaRepository:
    def __init__(self):
        self._usuarios: dict[int, dict] = {}
        self._transacoes: dict[int, dict] = {}
        self._usuario_id_seq = count(1)
        self._transacao_id_seq = count(1)

    # ---------- Usuários / Carteiras ----------

    def criar_usuario(
        self, nome: str, carteira_id: int, saldo_inicial: float = 0.0
    ) -> dict:
        usuario = {
            "id": carteira_id,
            "nome": nome,
            "saldo": saldo_inicial,
        }
        self._usuarios[carteira_id] = usuario
        return usuario

    def obter_usuario(self, carteira_id: int) -> Optional[dict]:
        return self._usuarios.get(carteira_id)

    def listar_usuarios(self) -> list[dict]:
        return list(self._usuarios.values())

    def carteira_existe(self, carteira_id: int) -> bool:
        return carteira_id in self._usuarios

    def atualizar_saldo(self, carteira_id: int, novo_saldo: float) -> None:
        self._usuarios[carteira_id]["saldo"] = novo_saldo

    # ---------- Transações ----------

    def criar_transacao(self, origem_id: int, destino_id: int, valor: float) -> dict:
        from datetime import datetime, timezone

        transacao_id = next(self._transacao_id_seq)
        transacao = {
            "id": transacao_id,
            "origem_usuario_id": origem_id,
            "destino_usuario_id": destino_id,
            "valor": valor,
            "data_hora": datetime.now(timezone.utc),
        }
        self._transacoes[transacao_id] = transacao
        return transacao

    def listar_transacoes(self) -> list[dict]:
        return sorted(self._transacoes.values(), key=lambda t: t["id"], reverse=True)


# Instância única. Em produção, poderá ser substituída por um repositório Azure.
_repositorio = MemoriaRepository()


def get_repository() -> MemoriaRepository:
    return _repositorio
