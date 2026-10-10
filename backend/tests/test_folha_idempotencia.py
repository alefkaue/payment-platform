"""Folha executada na hora não paga duas vezes num reenvio (relatório R1-30)."""

import pytest

from tests.helpers import Pessoa, depositar


@pytest.fixture
def folha(cliente):
    dono = Pessoa(cliente, "dono.folha@ex.com")
    f1, f2 = Pessoa(cliente, "func1.folha@ex.com"), Pessoa(cliente, "func2.folha@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, n, 10000)
    ids = []
    for f, salario in ((f1, "300.00"), (f2, "200.00")):
        r = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                         json={"nome": f.email.split("@")[0].title() + " Silva", "cpf": f.cpf, "salario": salario})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return dono, n, f1, f2, ids


def _pagar(cliente, dono, n, itens, **extra):
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": itens, **extra}, headers=dono.h(n))
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def test_reenviar_a_mesma_folha_nao_paga_de_novo(cliente, folha):
    dono, n, f1, f2, (a, b) = folha
    primeira = _pagar(cliente, dono, n, [{"funcionario_id": a}, {"funcionario_id": b}])
    segunda = _pagar(cliente, dono, n, [{"funcionario_id": b}, {"funcionario_id": a}])  # outra ordem
    assert {r["transacao_id"] for r in primeira} == {r["transacao_id"] for r in segunda}
    assert (f1.saldo(), f2.saldo(), dono.saldo(n)) == ("300.00", "200.00", "9500.00")


def test_com_chave_do_app_tambem_nao_repete(cliente, folha):
    dono, n, f1, _, (a, _b) = folha
    for _ in range(3):
        _pagar(cliente, dono, n, [{"funcionario_id": a}], idempotency_key="folha-outubro-1")
    assert f1.saldo() == "300.00"


def test_outra_competencia_ou_outro_valor_paga(cliente, folha):
    """Não bloqueia o que é legítimo: outro mês, adiantamento com outra descrição ou outro valor."""
    dono, n, f1, _, (a, _b) = folha
    _pagar(cliente, dono, n, [{"funcionario_id": a}], descricao="Salário 10/2026")
    _pagar(cliente, dono, n, [{"funcionario_id": a}], descricao="Salário 11/2026")
    _pagar(cliente, dono, n, [{"funcionario_id": a, "valor": "50.00"}], descricao="Salário 11/2026")
    assert f1.saldo() == "650.00"
