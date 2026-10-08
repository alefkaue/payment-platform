"""Depósito de demonstração: só existe com DEPOSITO_DEMO ligado."""

from app.core.config import get_settings
from tests.helpers import Pessoa


def test_deposito_demo_desligado_por_padrao(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com")
    r = cliente.post("/pagamentos/depositar-demo", json={"valor": "100.00"}, headers=ana.h())
    assert r.status_code == 403
    assert ana.saldo() == "0.00"


def test_deposito_demo_credita_a_conta_em_uso_e_permite_pix(cliente, monkeypatch):
    monkeypatch.setattr(get_settings(), "deposito_demo", True)
    ana = Pessoa(cliente, "ana@exemplo.com")
    bia = Pessoa(cliente, "bia@exemplo.com")
    assert cliente.post("/pagamentos/depositar-demo", json={"valor": "100.00"}, headers=ana.h()).status_code == 200
    assert ana.saldo() == "100.00"
    assert cliente.post("/pagamentos/depositar-demo", json={"valor": "0"}, headers=ana.h()).status_code == 422
    assert cliente.post("/pagamentos/depositar-demo", json={"valor": "20000"}, headers=ana.h()).status_code == 422
    cliente.post("/pix/chaves", json={"tipo": "email", "valor": "bia.pix@exemplo.com"}, headers=bia.h())
    assert ana.transferir({"chave": "bia.pix@exemplo.com"}, "40.00").status_code == 200
    assert bia.saldo() == "40.00"
