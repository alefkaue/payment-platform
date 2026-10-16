"""Prompt #2: pagamento confirma por SENHA; acima de LIMITE_AUTENTICACAO_ADICIONAL
exige também TOTP; sem facial. O limite é baixado via monkeypatch para isolar a regra
de autenticação do limite por-transação da conta."""
from decimal import Decimal

import app.services.pagamento_service as ps
from tests.helpers import Pessoa, conta_ref, depositar


def _limite_100(monkeypatch):
    monkeypatch.setattr(ps, "_limite_autenticacao_adicional", lambda: Decimal("100"))


def test_abaixo_ou_igual_ao_limite_so_senha(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    r = a.transferir(conta_ref(b.numero), "100")           # == limite: só senha, sem 2º fator
    assert r.status_code == 200 and r.json()["auth_metodo"] == "senha"
    assert a.transferir(conta_ref(b.numero), "50", senha=None).status_code == 401  # sem senha


def test_acima_do_limite_sem_totp_configurado_bloqueia(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    r = a.transferir(conta_ref(b.numero), "100.01")        # acima, mas sem 2º fator ativo
    assert r.status_code == 403 and "duas etapas" in r.json()["detail"].lower()


def test_acima_do_limite_com_senha_e_totp(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a = Pessoa(cliente, "a@ex.com").ativar_totp()
    b = Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    assert a.transferir(conta_ref(b.numero), "150", codigo_totp=a.codigo_totp()).status_code == 200


def test_acima_do_limite_senha_errada_nega(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a = Pessoa(cliente, "a@ex.com").ativar_totp()
    b = Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    assert a.transferir(conta_ref(b.numero), "150", senha="errada", codigo_totp=a.codigo_totp()).status_code == 401


def test_acima_do_limite_totp_errado_nega(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a = Pessoa(cliente, "a@ex.com").ativar_totp()
    b = Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    assert a.transferir(conta_ref(b.numero), "150", codigo_totp="000000").status_code == 401


def test_totp_reutilizado_nega(cliente, monkeypatch):
    _limite_100(monkeypatch)
    a = Pessoa(cliente, "a@ex.com").ativar_totp()
    b = Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    codigo = a.codigo_totp()
    assert a.transferir(conta_ref(b.numero), "120", codigo_totp=codigo).status_code == 200
    assert a.transferir(conta_ref(b.numero), "120", codigo_totp=codigo).status_code == 401  # anti-replay
