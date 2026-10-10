"""Limites de sessão (SEGURANCA.md item 3): máximo absoluto desde o login e queda
por inatividade. O refresh carrega `auth_time` (hora do login com senha + rosto)."""

import time

from tests.helpers import SENHA, Pessoa, login_completo


def _renovar(cliente, p: Pessoa, refresh: str):
    return cliente.post("/auth/refresh", json={"refresh_token": refresh}, headers={"X-Dispositivo-Id": p.dispositivo})


def _adiantar(monkeypatch, segundos: float):
    from app.services import auth_service

    real = time.time
    monkeypatch.setattr(auth_service, "_relogio", lambda: real() + segundos)


def test_renovacao_dentro_dos_limites_funciona(cliente):
    p = Pessoa(cliente, "p@ex.com")
    tk = login_completo(cliente, p.email, SENHA, p.dispositivo)
    r = _renovar(cliente, p, tk["refresh_token"])
    assert r.status_code == 200, r.text


def test_inatividade_derruba_a_sessao(cliente, monkeypatch):
    p = Pessoa(cliente, "p@ex.com")
    tk = login_completo(cliente, p.email, SENHA, p.dispositivo)
    _adiantar(monkeypatch, 31 * 60)  # padrão: 30 min sem renovar
    r = _renovar(cliente, p, tk["refresh_token"])
    assert r.status_code == 401 and "inatividade" in r.json()["detail"]


def test_tempo_maximo_vale_mesmo_renovando_sempre(cliente, monkeypatch):
    from app.core.config import get_settings

    from app.core import security

    monkeypatch.setattr(get_settings(), "sessao_max_horas", 1.0)
    monkeypatch.setattr(get_settings(), "sessao_inatividade_min", 999)
    p = Pessoa(cliente, "p@ex.com")
    tk = login_completo(cliente, p.email, SENHA, p.dispositivo)
    inicio = security.decodificar_token(tk["refresh_token"], "refresh")["auth_time"]
    # a renovação NÃO reinicia o relógio da sessão: o auth_time do login atravessa
    r = _renovar(cliente, p, tk["refresh_token"])
    assert r.status_code == 200, r.text
    refresh = r.json()["refresh_token"]
    assert security.decodificar_token(refresh, "refresh")["auth_time"] == inicio
    # 61 min depois do login, mesmo com refresh novinho, acabou
    _adiantar(monkeypatch, 61 * 60)
    r = _renovar(cliente, p, refresh)
    assert r.status_code == 401 and "tempo máximo" in r.json()["detail"]


def test_login_em_aparelho_novo_vai_para_a_atividade(cliente):
    p = Pessoa(cliente, "p@ex.com")
    login_completo(cliente, p.email, SENHA, "notebook-desconhecido")
    acoes = [e["acao"] for e in cliente.get("/seguranca/atividade", headers=p.h()).json()]
    assert "login_aparelho_novo" in acoes
