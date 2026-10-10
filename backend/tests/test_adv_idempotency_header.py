"""Contrato do header Idempotency-Key anunciado no CORS e nos documentos."""
import pytest

from tests.helpers import Pessoa, conta_ref, depositar


@pytest.mark.parametrize("segundo_valor", ["10", "20"])
@pytest.mark.xfail(strict=True, reason="ACHADO C1-03: header Idempotency-Key ignorado permite novo débito em reenvio")
def test_adv_header_idempotency_key_evitar_debito_repetido(cliente, segundo_valor):
    a, b = Pessoa(cliente, "header@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 100)
    h = {**a.h(), "Idempotency-Key": "c1-pagamento-unico"}
    primeira = cliente.post("/pagamentos/transferir", json={"destino": conta_ref(b.numero), "valor": "10"}, headers=h)
    segunda = cliente.post("/pagamentos/transferir", json={"destino": conta_ref(b.numero), "valor": segundo_valor}, headers=h)
    assert primeira.status_code == 200
    if segundo_valor == "10":
        assert segunda.status_code == 200 and primeira.json()["id"] == segunda.json()["id"]
    else:
        assert segunda.status_code == 409
    assert a.saldo() == "90.00" and b.saldo() == "10.00"
