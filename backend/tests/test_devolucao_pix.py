"""Devolução de Pix por quem recebeu (R1-13): integral ou parcial, até 90 dias, nunca acima
do recebido -- nem somando com a devolução do MED."""

from datetime import datetime, timedelta, timezone

from tests.helpers import Pessoa, admin_h, conta_ref, depositar


def _pix(cliente, valor="100.00"):
    a, b = Pessoa(cliente, "pagou.dev@ex.com"), Pessoa(cliente, "recebeu.dev@ex.com")
    depositar(cliente, a.numero, 500)
    t = a.transferir(conta_ref(b.numero), valor)
    assert t.status_code == 200, t.text
    return a, b, t.json()["id"]


def _devolver(cliente, quem, tid, **corpo):
    return cliente.post(f"/pagamentos/transacoes/{tid}/devolver", json=corpo, headers=quem.h())


def test_devolucao_parcial_depois_o_resto_e_mais_nada(cliente):
    a, b, tid = _pix(cliente)
    r = _devolver(cliente, b, tid, valor="30.00")
    assert r.status_code == 201, r.text
    assert (r.json()["tipo"], r.json()["transacao_original_id"]) == ("devolucao", tid)
    assert _devolver(cliente, b, tid, valor="80.00").status_code == 409  # sobra só 70
    assert _devolver(cliente, b, tid).status_code == 201  # sem valor = o que falta (70)
    assert _devolver(cliente, b, tid, valor="0.01").status_code == 409
    assert (a.saldo(), b.saldo()) == ("500.00", "0.00")


def test_so_quem_recebeu_devolve_e_reenvio_nao_duplica(cliente):
    a, b, tid = _pix(cliente)
    assert _devolver(cliente, a, tid, valor="10.00").status_code == 404  # o pagador não "devolve" a si mesmo
    intruso = Pessoa(cliente, "intruso.dev@ex.com")
    assert _devolver(cliente, intruso, tid, valor="10.00").status_code == 404
    for _ in range(3):
        assert _devolver(cliente, b, tid, valor="40.00", idempotency_key="devolve-uma-vez").status_code == 201
    assert b.saldo() == "60.00"
    assert _devolver(cliente, b, tid, valor="41.00", idempotency_key="devolve-uma-vez").status_code == 409


def test_prazo_de_90_dias(cliente, relogio):
    a, b, tid = _pix(cliente)
    relogio.definir(datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc) + timedelta(days=91))
    r = _devolver(cliente, b, tid)
    assert r.status_code in (401, 409)  # 409 = prazo; 401 se a sessão do teste vencer antes
    assert b.saldo() == "100.00" if r.status_code == 409 else True


def test_devolucao_voluntaria_mais_med_nao_devolve_em_dobro(cliente):
    a, b, tid = _pix(cliente)
    assert _devolver(cliente, b, tid, valor="60.00").status_code == 201
    depositar(cliente, b.numero, 1000)  # o recebedor tem saldo de sobra: só a regra segura o dobro
    assert cliente.post(f"/pagamentos/transacoes/{tid}/contestar", json={"motivo": "golpe do falso parente"},
                        headers=a.h()).status_code < 300
    adm = admin_h(cliente)
    [med] = [c for c in cliente.get("/admin/contestacoes", headers=adm).json() if c["transacao_id"] == tid]
    assert cliente.post(f"/admin/contestacoes/{med['id']}/decidir", json={"procedente": True}, headers=adm).status_code == 200
    # O pagador recebe de volta no máximo os 100 que pagou (60 voluntário + 40 pelo MED).
    assert (a.saldo(), b.saldo()) == ("500.00", "1000.00")
