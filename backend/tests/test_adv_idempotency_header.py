"""Contrato do header Idempotency-Key anunciado no CORS e nos documentos."""
import pytest

from tests.helpers import Pessoa, conta_ref, depositar


@pytest.mark.parametrize("segundo_valor", ["10", "20"])

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


def test_header_e_corpo_diferentes_e_recusado(cliente):
    """Correção do C1-03 (Claude): chave no header e outra no corpo é pedido ambíguo."""
    a, b = Pessoa(cliente, "ambiguo@ex.com"), Pessoa(cliente, "ambiguo.b@ex.com")
    depositar(cliente, a.numero, 100)
    r = cliente.post("/pagamentos/transferir", headers={**a.h(), "Idempotency-Key": "chave-a"},
                     json={"destino": conta_ref(b.numero), "valor": "10", "idempotency_key": "chave-b"})
    assert r.status_code == 400 and a.saldo() == "100.00"
    r = cliente.post("/pagamentos/transferir", headers={**a.h(), "Idempotency-Key": "chave-a"},
                     json={"destino": conta_ref(b.numero), "valor": "10", "idempotency_key": "chave-a"})
    assert r.status_code == 200 and a.saldo() == "90.00"


def test_header_vale_na_folha(cliente):
    dono, func = Pessoa(cliente, "dono.hdr@ex.com"), Pessoa(cliente, "func.hdr@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, n, 1000)
    fid = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                       json={"nome": "Func Silva", "cpf": func.cpf, "salario": "100.00"}).json()["id"]
    for descricao in ("Salário A", "Salário B"):  # descrições diferentes: só o header segura a repetição
        r = cliente.post("/empresas/atual/folha/pagar", headers={**dono.h(n), "Idempotency-Key": "folha-hdr-1"},
                         json={"itens": [{"funcionario_id": fid}], "descricao": descricao})
        assert r.status_code == 200, r.text
    assert func.saldo() == "100.00"
