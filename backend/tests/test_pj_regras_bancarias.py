"""Regras bancárias de PJ que a auditoria achou furadas (SECURITY_AUDIT.md A-01, A-02, A-05).

- Assinatura conjunta na Grande: acima do limite, NINGUÉM paga sozinho (nem admin).
- Alçada diária por usuário: fracionar (10 x R$ 900 numa alçada de R$ 1.000) e lote
  não driblam a alçada; a soma do dia é conferida de novo dentro do lock.
- Pendência: vence, quem lançou cancela, e quem foi suspenso não tem o pedido executado.
"""

from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import Pessoa, conta_ref, depositar
from tests.test_v9_seguranca import _aceitar, _convidar


def _empresa(cliente, porte, papeis, saldo=200000):
    dono = Pessoa(cliente, "dono@ex.com")
    n = dono.abrir_empresa(porte=porte)["numero"]
    depositar(cliente, n, saldo)
    eq = {}
    for nome, papel, alcada, extra in papeis:
        p = Pessoa(cliente, f"{nome}@ex.com")
        v = _convidar(cliente, dono, n, p, papel, alcada=alcada, **extra)
        assert v.status_code == 201, v.text
        assert _aceitar(cliente, p, v.json()["id"]).status_code == 200
        eq[nome] = (p, v.json()["id"])
    return dono, n, eq


def _decidir(cliente, pessoa, n, oid, aprovar=True):
    corpo = {"aprovar": aprovar}
    if aprovar:
        corpo["biometria"] = pessoa.prova()
    return cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json=corpo, headers=pessoa.h(n))


# ------------------------------------------------------------------ assinatura conjunta (Grande)


def test_admin_da_grande_nao_paga_sozinho_acima_do_limite(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "limite_duas_aprovacoes_reais", 5000.0)
    dono, n, eq = _empresa(cliente, "GRANDE", [("apr", "aprovador", 20000, {})])
    forn = Pessoa(cliente, "forn@ex.com")
    # abaixo do limite: admin paga sozinho, como antes
    assert dono.transferir(conta_ref(forn.numero), 4000, conta=n, biometria=dono.prova()).status_code == 200
    # acima: vira pendente, e o próprio admin conta como uma das duas assinaturas
    r = dono.transferir(conta_ref(forn.numero), 6000, conta=n, biometria=dono.prova())
    assert r.status_code == 202, r.text
    oid = r.json()["operacao_id"]
    p = cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).json()[0]
    assert p["aprovacoes_necessarias"] == 1
    assert dono.saldo(n) == "196000.00"
    apr = eq["apr"][0]
    r = _decidir(cliente, apr, n, oid)
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text
    assert dono.saldo(n) == "190000.00"


def test_pme_continua_com_admin_sem_limite(cliente):
    dono, n, _ = _empresa(cliente, "PME", [])
    forn = Pessoa(cliente, "forn@ex.com")
    assert dono.transferir(conta_ref(forn.numero), 50000, conta=n, biometria=dono.prova()).status_code == 200


# ------------------------------------------------------------------ alçada diária (fracionamento)


def test_fracionar_nao_dribla_a_alcada(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 1000, {})])
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    assert op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova()).status_code == 200
    # a 2ª passaria do teto do dia (alçada diária vazia = igual à alçada)
    r = op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova())
    assert r.status_code == 202, r.text
    assert dono.saldo(n) == "199100.00"


def test_alcada_diaria_maior_permite_varias_no_dia(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 1000, {"alcada_diaria": "3000"})])
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    cods = [op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova()).status_code for _ in range(4)]
    assert cods == [200, 200, 200, 202]
    # no dia seguinte o teto volta
    from app.core import tempo

    amanha = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
    tempo_original = tempo.agora
    try:
        tempo.agora = lambda: amanha
        assert op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova()).status_code == 200
    finally:
        tempo.agora = tempo_original


def test_lote_nao_dribla_a_alcada(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 1000, {})])
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    itens = [{"destino": conta_ref(forn.numero), "valor": "400"} for _ in range(4)]
    r = cliente.post("/pagamentos/lote", json={"itens": itens, "biometria": op.prova()}, headers=op.h(n))
    assert r.status_code == 200, r.text
    assert [i["situacao"] for i in r.json()] == ["concluida", "concluida", "pendente_aprovacao", "pendente_aprovacao"]


def test_alcada_diaria_conferida_dentro_do_lock(cliente, monkeypatch):
    """Simula a corrida: a checagem rápida (fora do lock) não vê a saída anterior;
    a de dentro do lock vê e manda para aprovação em vez de executar."""
    from app.repositories.repository import Repositorio

    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 1000, {})])
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    assert op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova()).status_code == 200
    monkeypatch.setattr(Repositorio, "saidas_do_usuario_hoje", lambda self, c, u: 0)
    r = op.transferir(conta_ref(forn.numero), 900, conta=n, biometria=op.prova())
    assert r.status_code == 202, r.text
    assert dono.saldo(n) == "199100.00"


def test_operacao_aprovada_nao_gasta_a_alcada_de_quem_aprova(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 100, {}), ("apr", "aprovador", 1000, {})])
    op, apr, forn = eq["op"][0], eq["apr"][0], Pessoa(cliente, "forn@ex.com")
    oid = op.transferir(conta_ref(forn.numero), 900, conta=n).json()["operacao_id"]
    assert _decidir(cliente, apr, n, oid).json()["status"] == "aprovada"
    # o aprovador ainda tem a alçada do dia inteira para o que ELE lançar
    assert apr.transferir(conta_ref(forn.numero), 1000, conta=n, biometria=apr.prova()).status_code == 200


def test_alcada_diaria_validada_e_aumento_e_sensivel(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 1000, {})])
    vid = eq["op"][1]
    r = cliente.patch(f"/empresas/atual/vinculos/{vid}", json={"alcada_diaria": "500"}, headers=dono.h(n))
    assert r.status_code == 400
    # aumentar o teto diário é dar poder: sem o rosto de quem concede, não passa
    r = cliente.patch(f"/empresas/atual/vinculos/{vid}", json={"alcada_diaria": "5000"}, headers=dono.h(n))
    assert r.status_code in (400, 401, 403), r.text
    r = cliente.patch(f"/empresas/atual/vinculos/{vid}", json={"alcada_diaria": "5000", "biometria": dono.prova()},
                      headers=dono.h(n))
    assert r.status_code == 200 and r.json()["alcada_diaria"] == "5000.00", r.text


# ------------------------------------------------------------------ ciclo de vida da pendência


@pytest.fixture()
def pendente(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 100, {})])
    op, vid = eq["op"]
    forn = Pessoa(cliente, "forn@ex.com")
    oid = op.transferir(conta_ref(forn.numero), 3000, conta=n).json()["operacao_id"]
    return dono, n, op, vid, oid


def test_quem_lancou_pode_cancelar(cliente, pendente):
    dono, n, op, _, oid = pendente
    r = _decidir(cliente, op, n, oid, aprovar=False)
    assert r.status_code == 200 and r.json()["status"] == "cancelada", r.text
    assert _decidir(cliente, dono, n, oid).status_code == 409
    # e continua sem poder aprovar a própria
    oid2 = op.transferir(conta_ref(Pessoa(cliente, "x@ex.com").numero), 3000, conta=n).json()["operacao_id"]
    assert _decidir(cliente, op, n, oid2).status_code == 403


def test_pendencia_de_quem_foi_suspenso_nao_executa(cliente, pendente):
    dono, n, op, vid, oid = pendente
    assert cliente.post(f"/empresas/atual/vinculos/{vid}/suspender", json={}, headers=dono.h(n)).status_code == 200
    r = _decidir(cliente, dono, n, oid)
    assert r.status_code == 409, r.text
    assert dono.saldo(n) == "200000.00"
    todas = cliente.get("/empresas/atual/pendentes?status=", headers=dono.h(n)).json()
    assert [p["status"] for p in todas if p["id"] == oid] == ["cancelada"]


def test_pendencia_vence(cliente, pendente, relogio):
    dono, n, _, _, oid = pendente
    relogio.definir(datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc) + timedelta(hours=73))
    assert cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).json() == []
    r = _decidir(cliente, dono, n, oid)
    assert r.status_code == 409 and "expirou" in r.json()["detail"]
    assert dono.saldo(n) == "200000.00"
