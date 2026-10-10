"""Outbox transacional: o webhook nasce na mesma transação do dinheiro (docs/BANCO.md)."""

from decimal import Decimal

import pytest

from app.db.models import AuthMetodo
from app.services.split_service import sem_split
from tests.helpers import Pessoa, admin_h, conta_ref, depositar
from tests.test_cobrancas import _cobrar, _empresa


@pytest.fixture
def loja(cliente, monkeypatch):
    from app.services import webhook_service

    enviados = []
    monkeypatch.setattr(webhook_service, "_enviar",
                        lambda url, corpo, headers: (enviados.append(corpo) or (True, "HTTP 200")))
    dono, n, _ = _empresa(cliente)
    r = cliente.post("/empresas/atual/webhooks", headers=dono.h(n), json={
        "url": "https://erp.exemplo.com/astro", "eventos": ["cobranca.paga", "pix.recebido"]})
    assert r.status_code == 201, r.text
    return dono, n, enviados


def _entregas(cliente, dono, n) -> list[dict]:
    return cliente.get("/empresas/atual/webhooks/entregas", headers=dono.h(n)).json()


def test_pagamento_grava_o_evento_junto_e_repetir_nao_duplica(cliente, loja):
    dono, n, enviados = loja
    pf = Pessoa(cliente, "cliente.outbox@ex.com")
    depositar(cliente, pf.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    h = {**pf.h(), "Idempotency-Key": "pagar-uma-vez"}
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=h).status_code == 200
    reenvio = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=h)  # devolve o original (C2-04)
    assert reenvio.status_code == 200
    assert [e["evento"] for e in _entregas(cliente, dono, n)] == ["cobranca.paga"]
    assert cliente.post("/admin/jobs/webhooks", headers=admin_h(cliente)).json()["processadas"] == 1
    assert len(enviados) == 1


def test_pix_recebido_vira_evento_e_reenvio_nao_duplica(cliente, loja):
    dono, n, _ = loja
    pf = Pessoa(cliente, "pagador.outbox@ex.com")
    depositar(cliente, pf.numero, 100)
    for _ in range(2):  # o app reenvia com a mesma chave (rede ruim)
        r = pf.transferir(conta_ref(n), "25.00", idempotency_key="pix-unico")
        assert r.status_code == 200, r.text
    assert pf.saldo() == "75.00"
    [e] = _entregas(cliente, dono, n)
    assert e["evento"] == "pix.recebido"


def test_estorno_e_pendencia_tambem_vao_pelo_outbox(cliente, loja):
    dono, n, _ = loja
    cliente.post("/empresas/atual/webhooks", headers=dono.h(n), json={
        "url": "https://erp2.exemplo.com/astro", "eventos": ["cobranca.estornada", "operacao.pendente"]})
    pf = Pessoa(cliente, "estorno.outbox@ex.com")
    depositar(cliente, pf.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h()).status_code == 200
    r = cliente.post(f"/cobrancas/{c['txid']}/estornar", json={}, headers=dono.h(n))
    assert r.status_code == 200, r.text
    assert "_entregas" not in r.json()  # detalhe interno não vaza na resposta
    eventos = sorted(e["evento"] for e in _entregas(cliente, dono, n))
    assert eventos == ["cobranca.estornada", "cobranca.paga"]


def test_pix_sem_saldo_nao_deixa_evento(cliente, loja):
    dono, n, _ = loja
    pf = Pessoa(cliente, "sem.saldo@ex.com")
    assert pf.transferir(conta_ref(n), "25.00").status_code == 400
    assert _entregas(cliente, dono, n) == []


def test_erro_ao_montar_o_evento_desfaz_o_dinheiro(cliente, loja):
    """Mesma transação: se o evento não pode ser gravado, o dinheiro também não sai."""
    from app.repositories import get_repository

    dono, n, _ = loja
    pf = Pessoa(cliente, "atomico@ex.com")
    depositar(cliente, pf.numero, 100)
    repo = get_repository()
    origem = repo.obter_conta_por_numero(pf.numero)
    destino = repo.obter_conta_por_numero(n)

    def quebra(_tx):
        raise RuntimeError("falhou ao gravar o evento")

    with pytest.raises(RuntimeError):
        repo.executar_movimento(origem_id=origem["carteira_id"], destino_id=destino["carteira_id"],
                                split=sem_split(Decimal("30.00")), tipo="transferencia",
                                auth_metodo=AuthMetodo.SENHA, evento=quebra)
    assert pf.saldo() == "100.00"
    assert _entregas(cliente, dono, n) == []
