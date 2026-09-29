"""
Repositório Postgres -- mesma interface pública do MemoriaRepository
(carteira_existe, criar_usuario, obter_usuario, listar_usuarios,
atualizar_saldo, salvar_embedding_facial, obter_embedding_facial,
executar_transferencia, listar_transacoes), pra services/routers não
precisarem saber qual dos dois está por trás de `get_repository()`.

Diferença de tipo que os services precisam saber: aqui `saldo`/`valor`
voltam como `decimal.Decimal` (Numeric no Postgres), não `float` -- Pydantic
converte Decimal pra float na resposta HTTP automaticamente, então a API não
muda, mas se algum código novo comparar `saldo == 400.0` direto no Python,
comparar Decimal com float funciona mas por segurança prefira
`Decimal(str(x))` do lado que for literal.

Atomicidade da transferência: `executar_transferencia` faz
`SELECT ... FOR UPDATE` nas duas carteiras (trava as linhas até o commit) e só
então checa saldo e escreve -- é o equivalente Postgres do lock em
memoria_repository.py. Sem isso, duas transferências simultâneas da mesma
carteira poderiam ler o mesmo saldo antes de qualquer uma escrever.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Carteira, HistoricoSaldo, Transacao, Usuario
from app.repositories.exceptions import SaldoInsuficienteError


class PostgresRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    # ---------- Usuários / Carteiras ----------

    def carteira_existe(self, carteira_id: int) -> bool:
        with self._session_factory() as sessao:
            return self._buscar_carteira(sessao, carteira_id) is not None

    def criar_usuario(self, carteira_id: int, nome: str, saldo_inicial: float = 0.0) -> dict:
        with self._session_factory() as sessao:
            usuario = Usuario(nome=nome)
            carteira = Carteira(
                chave=str(carteira_id), saldo=Decimal(str(saldo_inicial)), usuario=usuario
            )
            sessao.add(usuario)
            sessao.add(carteira)
            try:
                sessao.commit()
            except IntegrityError:
                # Defesa em profundidade: mesmo se dois cadastros com o mesmo
                # carteira_id chegarem ao mesmo tempo e ambos passarem pela
                # checagem em usuario_service.py, a constraint UNIQUE em
                # carteiras.chave garante que só um dos dois INSERTs vinga.
                sessao.rollback()
                raise ValueError(f"Já existe uma carteira com o ID {carteira_id}.") from None
            sessao.refresh(carteira)
            return self._carteira_para_dict(carteira)

    def obter_usuario(self, carteira_id: int) -> Optional[dict]:
        with self._session_factory() as sessao:
            carteira = self._buscar_carteira(sessao, carteira_id)
            return self._carteira_para_dict(carteira) if carteira else None

    def listar_usuarios(self) -> list[dict]:
        with self._session_factory() as sessao:
            carteiras = sessao.scalars(select(Carteira)).all()
            return [self._carteira_para_dict(c) for c in carteiras]

    def atualizar_saldo(self, carteira_id: int, novo_saldo: float) -> None:
        with self._session_factory() as sessao:
            carteira = self._buscar_carteira(sessao, carteira_id)
            carteira.saldo = Decimal(str(novo_saldo))
            sessao.commit()

    # ---------- Biometria facial (MFA) ----------

    def salvar_embedding_facial(self, carteira_id: int, embedding: list[float]) -> None:
        with self._session_factory() as sessao:
            carteira = self._buscar_carteira(sessao, carteira_id)
            carteira.usuario.embedding_facial = embedding
            sessao.commit()

    def obter_embedding_facial(self, carteira_id: int) -> Optional[list[float]]:
        with self._session_factory() as sessao:
            carteira = self._buscar_carteira(sessao, carteira_id)
            if carteira is None or carteira.usuario.embedding_facial is None:
                return None
            return list(carteira.usuario.embedding_facial)

    # ---------- Transações ----------

    def executar_transferencia(
        self,
        origem_carteira_id: int,
        destino_carteira_id: int,
        valor: float,
        verificacao_facial: dict,
    ) -> dict:
        with self._session_factory() as sessao:
            # FOR UPDATE trava as duas linhas até o commit -- uma segunda
            # transferência simultânea da mesma carteira espera aqui em vez de
            # ler um saldo que já está prestes a mudar. Ordena por chave antes
            # de travar pra sempre pedir os locks na mesma ordem entre
            # requisições concorrentes (evita deadlock entre A->B e B->A ao
            # mesmo tempo).
            chaves_em_ordem = sorted([str(origem_carteira_id), str(destino_carteira_id)])
            stmt = (
                select(Carteira).where(Carteira.chave.in_(chaves_em_ordem)).with_for_update()
            )
            carteiras = {c.chave: c for c in sessao.scalars(stmt).all()}
            carteira_origem = carteiras[str(origem_carteira_id)]
            carteira_destino = carteiras[str(destino_carteira_id)]

            valor_decimal = Decimal(str(valor))
            if carteira_origem.saldo < valor_decimal:
                raise SaldoInsuficienteError()

            saldo_origem_anterior = carteira_origem.saldo
            saldo_destino_anterior = carteira_destino.saldo
            carteira_origem.saldo -= valor_decimal
            carteira_destino.saldo += valor_decimal

            transacao = Transacao(
                origem_carteira_id=carteira_origem.id,
                destino_carteira_id=carteira_destino.id,
                valor=valor_decimal,
                verificacao_facial=verificacao_facial,
            )
            sessao.add(transacao)
            sessao.flush()  # popula transacao.id antes de referenciar no histórico

            sessao.add(
                HistoricoSaldo(
                    carteira_id=carteira_origem.id,
                    saldo_anterior=saldo_origem_anterior,
                    saldo_novo=carteira_origem.saldo,
                    transacao_id=transacao.id,
                )
            )
            sessao.add(
                HistoricoSaldo(
                    carteira_id=carteira_destino.id,
                    saldo_anterior=saldo_destino_anterior,
                    saldo_novo=carteira_destino.saldo,
                    transacao_id=transacao.id,
                )
            )

            sessao.commit()
            return self._transacao_para_dict(transacao, carteira_origem.chave, carteira_destino.chave)

    def listar_transacoes(self) -> list[dict]:
        with self._session_factory() as sessao:
            transacoes = sessao.scalars(
                select(Transacao).order_by(Transacao.id.desc())
            ).all()
            resultado = []
            for t in transacoes:
                origem = sessao.get(Carteira, t.origem_carteira_id)
                destino = sessao.get(Carteira, t.destino_carteira_id)
                resultado.append(self._transacao_para_dict(t, origem.chave, destino.chave))
            return resultado

    # ---------- Helpers internos ----------

    @staticmethod
    def _buscar_carteira(sessao: Session, carteira_id: int) -> Optional[Carteira]:
        return sessao.scalar(select(Carteira).where(Carteira.chave == str(carteira_id)))

    @staticmethod
    def _carteira_para_dict(carteira: Carteira) -> dict:
        # int(chave) só funciona enquanto carteira_id continuar sendo o número
        # que o usuário digita. Quando a chave virar estilo PIX (string
        # aleatória), isso -- e o schema UsuarioResponse -- precisam mudar
        # junto para devolver a chave como string.
        return {
            "carteira_id": int(carteira.chave),
            "nome": carteira.usuario.nome,
            "saldo": carteira.saldo,
        }

    @staticmethod
    def _transacao_para_dict(transacao: Transacao, chave_origem: str, chave_destino: str) -> dict:
        return {
            "id": transacao.id,
            "origem_carteira_id": int(chave_origem),
            "destino_carteira_id": int(chave_destino),
            "valor": transacao.valor,
            "data_hora": transacao.criado_em or datetime.now(timezone.utc),
            "verificacao_facial": transacao.verificacao_facial,
        }
