"""Operação aprovada que ficou "executando" (queda no meio da execução): o job concilia
pelo banco, sem reexecutar (docs/BANCO.md, pendência de produção)."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import Pessoa, admin_h, conta_ref
from tests.test_pj_regras_bancarias import _decidir, pendente  # noqa: F401 (fixture)

AGORA = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def _status(cliente, dono, n, oid) -> dict:
    todas = cliente.get("/empresas/atual/pendentes?status=", headers=dono.h(n)).json()
    return next(p for p in todas if p["id"] == oid)


def _cai_depois_do_movimento(monkeypatch):
    """Simula a queda do processo depois do débito e antes de gravar o resultado."""
    from app.repositories.repository import Repositorio

    def cai(*_a, **_k):
        raise RuntimeError("processo caiu")

    monkeypatch.setattr(Repositorio, "concluir_pendente", cai)


def _cai_antes_do_movimento(monkeypatch):
    from app.services import pagamento_service

    def cai(*_a, **_k):
        raise RuntimeError("processo caiu")

    monkeypatch.setattr(pagamento_service, "transferir", cai)


def _rodar_job(cliente, relogio, minutos_depois: int):
    h = admin_h(cliente)
    relogio.definir(AGORA + timedelta(minutes=minutos_depois))
    r = cliente.post("/admin/jobs/conciliar-pendentes", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_dinheiro_saiu_vira_aprovada_sem_debitar_de_novo(cliente, pendente, monkeypatch, relogio):  # noqa: F811
    dono, n, _, _, oid = pendente
    _cai_depois_do_movimento(monkeypatch)
    with pytest.raises(RuntimeError):
        _decidir(cliente, dono, n, oid)
    monkeypatch.undo()
    assert dono.saldo(n) == "197000.00"
    assert _status(cliente, dono, n, oid)["status"] == "executando"

    assert _rodar_job(cliente, relogio, 5)["conciliadas"] == 0  # ainda pode estar rodando
    r = _rodar_job(cliente, relogio, 11)
    assert r == {"conciliadas": 1, "aprovadas": 1, "falharam": 0}
    p = _status(cliente, dono, n, oid)
    assert p["status"] == "aprovada" and p["resultado"]["conciliada"] and p["resultado"]["transacao_id"]
    assert dono.saldo(n) == "197000.00"  # nada foi debitado de novo
    assert _rodar_job(cliente, relogio, 30)["conciliadas"] == 0  # idempotente


def test_dinheiro_nao_saiu_vira_falhou(cliente, pendente, monkeypatch, relogio):  # noqa: F811
    dono, n, _, _, oid = pendente
    _cai_antes_do_movimento(monkeypatch)
    with pytest.raises(RuntimeError):
        _decidir(cliente, dono, n, oid)
    monkeypatch.undo()
    assert _status(cliente, dono, n, oid)["status"] == "executando"
    r = _rodar_job(cliente, relogio, 11)
    assert r == {"conciliadas": 1, "aprovadas": 0, "falharam": 1}
    p = _status(cliente, dono, n, oid)
    assert p["status"] == "falhou" and "Nada foi debitado" in p["resultado"]["erro"]
    assert dono.saldo(n) == "200000.00"


def test_transacao_de_outra_pendente_nao_confunde(cliente, pendente, monkeypatch, relogio):  # noqa: F811
    """A pendente 1 não pode ser dada como paga pela transação da pendente 12 (LIKE)."""
    from app.db.base import SessionLocal
    from app.db.models import OperacaoPendente

    dono, n, op, _, oid = pendente
    forn = Pessoa(cliente, "outro.forn@ex.com")
    outras = [op.transferir(conta_ref(forn.numero), 3000, conta=n).json()["operacao_id"] for _ in range(11)]
    assert _decidir(cliente, dono, n, outras[-1]).status_code == 200  # executa "pendente-<oid+11>"
    with SessionLocal() as s:  # a primeira "travou" sem mover dinheiro
        p = s.get(OperacaoPendente, oid)
        p.status, p.decidido_em = "executando", AGORA
        s.commit()
    _rodar_job(cliente, relogio, 11)
    assert _status(cliente, dono, n, oid)["status"] == "falhou"


def test_job_so_para_admin(cliente, pendente):  # noqa: F811
    dono, n, _, _, _ = pendente
    assert cliente.post("/admin/jobs/conciliar-pendentes", headers=dono.h(n)).status_code == 403
