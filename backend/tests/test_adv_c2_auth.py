"""Ataques adicionais à recuperação e ao TOTP dos commits revisados."""
from datetime import date

import jwt
import pytest

from app.core import config, totp
from tests.helpers import ADMIN, Pessoa, SENHA, login_completo
from tests.test_senha import NASCIMENTO, _definir_nascimento, _iniciar, _concluir
from tests.test_config_producao import producao  # noqa: F401
from tests.test_admin_totp import SEGREDO, com_totp, _senha_admin  # noqa: F401


def test_recuperacao_alias_e_ip_forjado_nao_abrem_limite(cliente, monkeypatch):
    a = Pessoa(cliente, "c2.alias@ex.com")
    monkeypatch.setattr(config.get_settings(), "recuperacao_max_conta_hora", 3)
    aliases = [a.email.upper(), " " + a.email + " ", a.cpf,
               f"{a.cpf[:3]}.{a.cpf[3:6]}.{a.cpf[6:9]}-{a.cpf[9:]}"]
    for i, alias in enumerate(aliases):
        r = cliente.post("/auth/recuperacao", headers={"X-Forwarded-For": f"198.51.100.{i}", "X-Dispositivo-Id": f"c2-{i}"},
                         json={"login": alias, "data_nascimento": NASCIMENTO})
        assert r.status_code == (201 if i < 3 else 429), r.text


def test_recuperacao_limite_ip_entre_contas_inexistentes(cliente, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "recuperacao_max_ip_hora", 2)
    for i in range(3):
        assert _iniciar(cliente, f"c2.inexistente{i}@ex.com", NASCIMENTO, "c2-dev").status_code == (201 if i < 2 else 429)


@pytest.mark.parametrize("ataque", ["assinatura", "cifrado", "expirado", "admin", "outro-aparelho"])
def test_recuperacao_tokens_adulterados_nao_mudam_senha(cliente, ataque):
    a = Pessoa(cliente, "c2.recupera@ex.com")
    _definir_nascimento(a.email, date(1990, 5, 17))
    etapa = _iniciar(cliente, ADMIN["email"] if ataque == "admin" else a.email, NASCIMENTO, "c2-dev").json()
    if ataque in ("assinatura", "cifrado", "expirado"):
        token = etapa["recuperacao_token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        if ataque == "assinatura":
            payload["sub"] = "1"
            segredo = "c2-assinatura-forjada-sem-valor-real"
        else:
            segredo = config.get_settings().jwt_secret
            if ataque == "cifrado":
                payload["u"] = "cifrado-adulterado"
            else:
                payload["exp"] = 1
        etapa["recuperacao_token"] = jwt.encode(payload, segredo, algorithm="HS256", headers={"typ": "rec+jwt"})
    assert _concluir(cliente, etapa, "outro" if ataque == "outro-aparelho" else "c2-dev").status_code == 401
    assert cliente.get("/auth/eu", headers=a.h()).status_code == 200


def test_recuperacao_revoga_refresh_e_access_de_todas_as_sessoes(cliente):
    a = Pessoa(cliente, "c2.sessoes@ex.com")
    _definir_nascimento(a.email, date(1990, 5, 17))
    notebook = login_completo(cliente, a.email, SENHA, "c2-note")
    etapa = _iniciar(cliente, a.email, NASCIMENTO, "c2-novo").json()
    assert _concluir(cliente, etapa, "c2-novo").status_code == 204
    assert cliente.get("/auth/eu", headers=a.h()).status_code == 401
    h = {"X-Dispositivo-Id": "c2-note", "Authorization": f"Bearer {notebook['access_token']}"}
    assert cliente.get("/auth/eu", headers=h).status_code == 401
    assert cliente.post("/auth/refresh", headers=h, json={"refresh_token": notebook["refresh_token"]}).status_code == 401
    # Mesmo token reutilizado com desafio novo continua proibido.
    etapa["desafio"] = _iniciar(cliente, a.email, NASCIMENTO, "c2-novo").json()["desafio"]
    assert _concluir(cliente, etapa, "c2-novo", "Terceira-Chave#99x").status_code == 401


def test_totp_janela_reuso_e_bruteforce_no_mesmo_token(cliente, com_totp, monkeypatch):
    from app.services import auth_service
    instante = 1800000000
    monkeypatch.setattr(auth_service, "_relogio", lambda: instante)
    etapa = _senha_admin(cliente)
    token = etapa["mfa_token"]
    fora = totp.codigo(SEGREDO, instante // 30 - 2)
    r = cliente.post("/auth/login/totp", json={"mfa_token": token, "codigo": fora})
    assert r.status_code == 401
    codigo = totp.codigo(SEGREDO, instante // 30 + 1)
    assert cliente.post("/auth/login/totp", json={"mfa_token": token, "codigo": codigo}).status_code == 200
    outro = _senha_admin(cliente)["mfa_token"]
    assert cliente.post("/auth/login/totp", json={"mfa_token": outro, "codigo": codigo}).status_code == 401
    monkeypatch.setattr(config.get_settings(), "login_max_tentativas_conta", 3)
    errado = "000000" if codigo != "000000" else "111111"
    assert cliente.post("/auth/login/totp", json={"mfa_token": outro, "codigo": errado}).status_code == 401
    assert cliente.post("/auth/login/totp", json={"mfa_token": outro, "codigo": errado}).status_code == 429


def test_admin_producao_sem_segredo_nao_sobe(producao):
    producao.setenv("ADMIN_IPS_PERMITIDOS", "198.51.100.1")
    producao.setenv("ADMIN_TOTP_SEGREDO", "")
    with pytest.raises(RuntimeError, match="ADMIN_TOTP_SEGREDO"):
        config.get_settings()
