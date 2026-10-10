"""Regressões: saldo/ledger, entradas adversariais e invariantes no banco."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import SessionLocal
from app.db.models import Carteira, HistoricoSaldo, Transacao, AuthMetodo
from app.repositories import get_repository
from app.repositories.exceptions import IdempotenciaConflitanteError
from app.services.split_service import ResultadoSplit, sem_split
from tests.helpers import Pessoa, depositar


def _contas(cliente):
    a, b = Pessoa(cliente, "integridade-a@ex.com"), Pessoa(cliente, "integridade-b@ex.com")
    depositar(cliente, a.numero, 100)
    repo = get_repository()
    return repo, repo.obter_conta_por_numero(a.numero)["carteira_id"], repo.obter_conta_por_numero(b.numero)["carteira_id"]


def test_todo_historico_novo_tem_transacao_e_conserva_saldo(cliente):
    repo, a, b = _contas(cliente)
    t = repo.executar_movimento(origem_id=a, destino_id=b, split=sem_split(Decimal("12.34")),
                               tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
    with SessionLocal() as s:
        assert s.scalar(select(func.count(HistoricoSaldo.id)).where(HistoricoSaldo.transacao_id.is_(None))) == 0
        hs = s.scalars(select(HistoricoSaldo).where(HistoricoSaldo.transacao_id == t["id"])).all()
        assert len(hs) == 2
        assert sum((h.saldo_novo - h.saldo_anterior + h.bloqueado_novo - h.bloqueado_anterior for h in hs), Decimal(0)) == 0
        assert s.scalar(select(func.sum(Carteira.saldo + Carteira.saldo_bloqueado))) == 0


@pytest.mark.parametrize("sql", [
    "UPDATE carteiras SET saldo = -1 WHERE id = :id",
    "UPDATE carteiras SET saldo_bloqueado = -1 WHERE id = :id",
    "UPDATE carteiras SET titular_tipo = 'PJ' WHERE id = :id",
    "UPDATE carteiras SET usuario_id = 987654 WHERE id = :id",
])
def test_banco_recusa_saldo_titular_e_fk_invalidos(cliente, sql):
    _, a, _ = _contas(cliente)
    with SessionLocal() as s, pytest.raises(IntegrityError):
        s.execute(text(sql), {"id": a})
        s.commit()


def test_idempotencia_nao_reutiliza_transferencia_para_deposito(cliente):
    repo, a, b = _contas(cliente)
    args = dict(origem_id=a, destino_id=b, split=sem_split(Decimal("5")), auth_metodo=AuthMetodo.SENHA,
                idempotency_key=f"{a}:mesma-operacao")
    repo.executar_movimento(**args, tipo="transferencia")
    with pytest.raises(IdempotenciaConflitanteError):
        repo.executar_movimento(**args, tipo="deposito")


@pytest.mark.parametrize("bruto,liquido,cbs", [("-1","-1","0"), ("1","2","0"), ("NaN","1","0"), ("1","0.99","0")])
def test_repositorio_recusa_criacao_de_dinheiro(cliente, bruto, liquido, cbs):
    repo, a, b = _contas(cliente)
    split = ResultadoSplit(Decimal(bruto), Decimal(cbs), Decimal("0"), Decimal(liquido), False)
    with pytest.raises(ValueError):
        repo.executar_movimento(origem_id=a, destino_id=b, split=split, tipo="transferencia", auth_metodo=AuthMetodo.SENHA)


def test_devolucao_nao_pode_ser_repetida(cliente):
    repo, a, b = _contas(cliente)
    t = repo.executar_movimento(origem_id=a, destino_id=b, split=sem_split(Decimal("10")),
                               tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
    assert repo.devolver(transacao_id=t["id"], valor_maximo=Decimal("10"), tipo="devolucao", autor_usuario_id=None)["valor_devolvido"] == 10
    assert repo.devolver(transacao_id=t["id"], valor_maximo=Decimal("10"), tipo="devolucao", autor_usuario_id=None)["valor_devolvido"] == 0
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Transacao.id)).where(Transacao.transacao_original_id == t["id"])) == 1


def test_remover_aparelho_preserva_sessoes_e_transacoes(cliente):
    repo, a, b = _contas(cliente)
    usuario = repo.obter_conta(a)["usuario_id"]
    d = repo.listar_dispositivos(usuario)[0]
    # Já há refresh apontando para o aparelho; exclusão física violaria a FK.
    assert repo.remover_dispositivo(usuario, d["id"])
    assert repo.listar_dispositivos(usuario) == []
    assert repo.dispositivo_por_id(d["id"]) is not None
    assert repo.dispositivo_por_id(d["id"])["bloqueado"]


def test_producao_nao_movimenta_identidade_pendente(cliente, monkeypatch):
    from app.core.config import get_settings
    repo, a, b = _contas(cliente)
    monkeypatch.setattr(get_settings(), "ambiente", "producao")
    with pytest.raises(ValueError, match="Identidade"):
        repo.executar_movimento(origem_id=a, destino_id=b, split=sem_split(Decimal("10")),
                               tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
    assert repo.obter_conta(a)["saldo"] == 100
    assert repo.obter_conta(b)["saldo"] == 0
