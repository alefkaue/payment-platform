"""2º fator do admin da plataforma: código TOTP do app autenticador (SECURITY_AUDIT A-15)."""

import time

import pytest

from app.core import config, totp
from tests.helpers import ADMIN, SENHA, Pessoa

# RFC 6238, apêndice B: segredo ASCII "12345678901234567890" em base32.
SEGREDO_RFC = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
SEGREDO = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


@pytest.mark.parametrize(("instante", "esperado"), [(59, "287082"), (1111111109, "081804"),
                                                    (1234567890, "005924"), (2000000000, "279037")])
def test_vetores_da_rfc_6238(instante, esperado):
    assert totp.codigo(SEGREDO_RFC, instante // 30) == esperado
    assert totp.passo_do_codigo(SEGREDO_RFC, esperado, instante) == instante // 30


def test_codigo_fora_da_janela_ou_malformado_nao_vale():
    assert totp.passo_do_codigo(SEGREDO_RFC, "287082", 59 + 90) is None  # 3 passos depois
    for ruim in ("", "28708", "2870823", "abcdef", None):
        assert totp.passo_do_codigo(SEGREDO_RFC, ruim, 59) is None  # type: ignore[arg-type]
    assert not totp.segredo_valido("CURTO234")
    assert not totp.segredo_valido("não é base32!")
    assert totp.segredo_valido(SEGREDO)


@pytest.fixture
def com_totp(monkeypatch):
    monkeypatch.setattr(config.get_settings(), "admin_totp_segredo", SEGREDO)


def _senha_admin(cliente):
    r = cliente.post("/auth/login", json={"email": ADMIN["email"], "senha": ADMIN["senha"]})
    assert r.status_code == 200, r.text
    return r.json()


def _agora() -> str:
    return totp.codigo(SEGREDO, int(time.time()) // 30)


def test_admin_com_segredo_precisa_do_codigo(cliente, com_totp):
    etapa = _senha_admin(cliente)
    assert etapa["mfa_requerido"] is True and etapa["fator"] == "totp"
    assert etapa["access_token"] is None and etapa["desafio"] is None
    errado = "000000" if _agora() != "000000" else "111111"
    r = cliente.post("/auth/login/totp", json={"mfa_token": etapa["mfa_token"], "codigo": errado})
    assert r.status_code == 401
    r = cliente.post("/auth/login/totp", json={"mfa_token": etapa["mfa_token"], "codigo": _agora()})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert cliente.get("/admin/contas", headers=h).status_code == 200


def test_codigo_vale_uma_vez(cliente, com_totp):
    codigo = _agora()
    r = cliente.post("/auth/login/totp", json={"mfa_token": _senha_admin(cliente)["mfa_token"], "codigo": codigo})
    assert r.status_code == 200, r.text
    r = cliente.post("/auth/login/totp", json={"mfa_token": _senha_admin(cliente)["mfa_token"], "codigo": codigo})
    assert r.status_code == 401


def test_etapas_nao_se_misturam(cliente, com_totp):
    """O token da etapa de rosto não serve no TOTP, e o do admin não serve no rosto."""
    ana = Pessoa(cliente, "ana.totp@ex.com")
    h = {"X-Dispositivo-Id": ana.dispositivo}
    etapa_ana = cliente.post("/auth/login", json={"email": ana.email, "senha": SENHA}, headers=h).json()
    assert etapa_ana["fator"] == "rosto"
    r = cliente.post("/auth/login/totp", json={"mfa_token": etapa_ana["mfa_token"], "codigo": _agora()}, headers=h)
    assert r.status_code == 401
    etapa_admin = _senha_admin(cliente)
    r = cliente.post("/auth/login/mfa", json={"mfa_token": etapa_admin["mfa_token"],
                                              "biometria": {"desafio_id": "x" * 20, "quadros": ["a", "b"]}})
    assert r.status_code == 401


def test_codigo_errado_conta_no_limite_de_login(cliente, com_totp, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "login_max_tentativas_conta", 3)
    errado = "000000" if _agora() != "000000" else "111111"
    for _ in range(3):
        cliente.post("/auth/login/totp", json={"mfa_token": _senha_admin(cliente)["mfa_token"], "codigo": errado})
    r = cliente.post("/auth/login", json={"email": ADMIN["email"], "senha": ADMIN["senha"]})
    assert r.status_code == 429


def test_sem_segredo_o_admin_de_desenvolvimento_continua_como_antes(cliente):
    etapa = _senha_admin(cliente)
    assert etapa["mfa_requerido"] is False and etapa["access_token"]
