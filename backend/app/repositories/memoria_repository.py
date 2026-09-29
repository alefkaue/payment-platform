"""
Repositório em memória (sem banco de dados). Usado quando DATABASE_URL não está
configurada -- ver app/repositories/__init__.py, que decide entre este e o
PostgresRepository sem que services/routers precisem saber qual dos dois está
ativo.

Importante: este repositório inicia SEMPRE vazio. Não há usuários pré-cadastrados
("seed") -- toda carteira só existe depois que alguém a cria pelo front-end,
informando o próprio `carteira_id`.
"""

import threading
from datetime import datetime, timezone
from itertools import count
from typing import Optional

from app.repositories.exceptions import SaldoInsuficienteError


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

        # Lock único pra todo o repositório. Simples de propósito -- um lock por
        # carteira daria mais paralelismo, mas pra um repositório de
        # desenvolvimento/demo (single-process) essa granularidade não compensa a
        # complexidade. É isso que fecha a condição de corrida em
        # `executar_transferencia`: sem ele, duas transferências simultâneas da
        # mesma carteira podiam as duas passar no "saldo suficiente" antes de
        # qualquer uma debitar.
        self._lock = threading.Lock()

    # ---------- Usuários / Carteiras ----------

    def carteira_existe(self, carteira_id: int) -> bool:
        return carteira_id in self._usuarios

    def criar_usuario(self, carteira_id: int, nome: str, saldo_inicial: float = 0.0) -> dict:
        # Mesmo lock da transferência: sem isso, dois cadastros simultâneos com o
        # mesmo carteira_id passariam os dois no "carteira_existe" (checado antes,
        # em usuario_service.py) e o segundo sobrescreveria o primeiro em silêncio.
        with self._lock:
            if carteira_id in self._usuarios:
                raise ValueError(f"Já existe uma carteira com o ID {carteira_id}.")
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

    def executar_transferencia(
        self,
        origem_carteira_id: int,
        destino_carteira_id: int,
        valor: float,
        verificacao_facial: dict,
    ) -> dict:
        """Checa saldo, debita, credita e registra a transação -- tudo dentro do
        MESMO lock. `pagamento_service.py` já validou antes de chamar isto que as
        duas carteiras existem e que o MFA passou; aqui só entra a parte que
        precisa ser atômica (dinheiro). Levanta SaldoInsuficienteError se não
        tiver saldo -- o service traduz isso pra HTTPException 400."""
        with self._lock:
            usuario_origem = self._usuarios[origem_carteira_id]
            usuario_destino = self._usuarios[destino_carteira_id]

            if usuario_origem["saldo"] < valor:
                raise SaldoInsuficienteError()

            usuario_origem["saldo"] -= valor
            usuario_destino["saldo"] += valor

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
