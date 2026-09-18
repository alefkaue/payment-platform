"""
Repositório em memória (sem banco de dados).

Toda a lógica de acesso a dados fica isolada aqui atrás de uma interface simples.
Quando o projeto migrar para Azure (ex: Azure SQL Database ou Azure Cosmos DB),
basta criar um novo repositório (ex: AzureSqlRepository) com os mesmos métodos
e trocar a instância usada em `get_repository()` -- o resto do código
(services, routers) não precisa mudar.

Importante: este repositório inicia SEMPRE vazio. Não há usuários pré-cadastrados
("seed") -- toda carteira só existe depois que alguém a cria pelo front-end,
informando o próprio `carteira_id`.
"""

from itertools import count
from typing import Optional


class MemoriaRepository:
    def __init__(self):
        # Chave do dict = carteira_id (escolhido pelo usuário na criação da conta).
        self._usuarios: dict[int, dict] = {}
        self._transacoes: dict[int, dict] = {}
        self._transacao_id_seq = count(1)

        # Embeddings faciais (MFA) guardados separados dos dados da conta -- de
        # propósito. É a mesma lógica de nunca guardar senha junto com o resto do
        # cadastro: se um dia isso for para dois datastores reais (ex: dados da conta
        # no Cosmos DB, template biométrico em um serviço dedicado/criptografado), a
        # divisão já está pronta aqui. Nunca guardamos a foto em si, só o vetor.
        self._embeddings_faciais: dict[int, list[float]] = {}

    # ---------- Usuários / Carteiras ----------

    def carteira_existe(self, carteira_id: int) -> bool:
        return carteira_id in self._usuarios

    def criar_usuario(self, carteira_id: int, nome: str, saldo_inicial: float = 0.0) -> dict:
        usuario = {
            "carteira_id": carteira_id,
            "nome": nome,
            "saldo": saldo_inicial,
        }
        self._usuarios[carteira_id] = usuario
        return usuario

    def obter_usuario(self, carteira_id: int) -> Optional[dict]:
        return self._usuarios.get(carteira_id)

    def listar_usuarios(self) -> list[dict]:
        return list(self._usuarios.values())

    def atualizar_saldo(self, carteira_id: int, novo_saldo: float) -> None:
        self._usuarios[carteira_id]["saldo"] = novo_saldo

    # ---------- Biometria facial (MFA) ----------

    def salvar_embedding_facial(self, carteira_id: int, embedding: list[float]) -> None:
        self._embeddings_faciais[carteira_id] = embedding

    def obter_embedding_facial(self, carteira_id: int) -> Optional[list[float]]:
        return self._embeddings_faciais.get(carteira_id)

    # ---------- Transações ----------

    def criar_transacao(
        self,
        origem_carteira_id: int,
        destino_carteira_id: int,
        valor: float,
        verificacao_facial: dict,
    ) -> dict:
        from datetime import datetime, timezone

        transacao_id = next(self._transacao_id_seq)
        transacao = {
            "id": transacao_id,
            "origem_carteira_id": origem_carteira_id,
            "destino_carteira_id": destino_carteira_id,
            "valor": valor,
            "data_hora": datetime.now(timezone.utc),
            "verificacao_facial": verificacao_facial,
        }
        self._transacoes[transacao_id] = transacao
        return transacao

    def listar_transacoes(self) -> list[dict]:
        return sorted(self._transacoes.values(), key=lambda t: t["id"], reverse=True)


# Instância única (singleton) usada pela aplicação inteira.
# Isolar aqui é o que vai permitir trocar por um repositório Azure no futuro
# sem tocar em services/routers. Inicia vazia -- sem dados de demonstração.
_repositorio = MemoriaRepository()


def get_repository() -> MemoriaRepository:
    return _repositorio
