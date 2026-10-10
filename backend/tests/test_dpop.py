"""Prova de posse da chave (DPoP, RFC 9449) -- SEGURANCA.md item 2.

Simula o ataque de roubo de token: quem copia access/refresh (e até o
X-Dispositivo-Id) mas não tem a chave privada do aparelho não consegue usar.
"""

import secrets

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from tests.helpers import QUADROS, SENHA, Pessoa


class Chave:
    """O que o app faz com WebCrypto: par ECDSA P-256 e provas ES256."""

    def __init__(self):
        self.privada = ec.generate_private_key(ec.SECP256R1())
        self.jwk = ECAlgorithm.to_jwk(self.privada.public_key(), as_dict=True)

    def prova(self, metodo: str, caminho: str, *, access_token: str | None = None, iat: float | None = None,
              jti: str | None = None, jwk: dict | None = None) -> str:
        from app.core import dpop, tempo

        corpo = {"jti": jti or secrets.token_urlsafe(16), "htm": metodo,
                 "htu": f"https://api.astro.test{caminho}",
                 "iat": int(iat if iat is not None else tempo.agora().timestamp())}
        if access_token:
            corpo["ath"] = dpop.hash_access_token(access_token)
        return jwt.encode(corpo, self.privada, algorithm="ES256",
                          headers={"typ": "dpop+jwt", "jwk": jwk or self.jwk})


@pytest.fixture()
def dpop_ligado(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "dpop_obrigatorio", True)


def _entrar(cliente, p: Pessoa, chave: Chave) -> dict:
    h = {"X-Dispositivo-Id": p.dispositivo}
    r = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA},
                     headers={**h, "DPoP": chave.prova("POST", "/auth/login")})
    assert r.status_code == 200, r.text
    e = r.json()
    r = cliente.post("/auth/login/mfa", headers={**h, "DPoP": chave.prova("POST", "/auth/login/mfa")}, json={
        "mfa_token": e["mfa_token"], "biometria": {"desafio_id": e["desafio"]["desafio_id"], "quadros": QUADROS}})
    assert r.status_code == 200, r.text
    return r.json()


def _get(cliente, caminho, tokens, p, prova):
    return cliente.get(caminho, headers={"Authorization": f"Bearer {tokens['access_token']}",
                                         "X-Dispositivo-Id": p.dispositivo, **({"DPoP": prova} if prova else {})})


def test_login_sem_dpop_e_recusado(cliente, dpop_ligado):
    # recusa antes de conferir a senha (não vira oráculo de senha certa/errada)
    r = cliente.post("/auth/login", json={"email": "ninguem@ex.com", "senha": SENHA})
    assert r.status_code == 400 and "DPoP" in r.json()["detail"]


def test_fluxo_completo_com_a_chave_do_aparelho(cliente):
    p = Pessoa(cliente, "p@ex.com")
    chave = Chave()
    tk = _entrar(cliente, p, chave)
    r = _get(cliente, "/contas/atual", tk, p, chave.prova("GET", "/contas/atual", access_token=tk["access_token"]))
    assert r.status_code == 200, r.text


def test_token_roubado_sem_a_chave_nao_serve(cliente):
    p = Pessoa(cliente, "p@ex.com")
    tk = _entrar(cliente, p, Chave())
    # sem prova nenhuma
    assert _get(cliente, "/contas/atual", tk, p, None).status_code == 401
    # com prova de OUTRA chave (a do atacante)
    atacante = Chave()
    r = _get(cliente, "/contas/atual", tk, p, atacante.prova("GET", "/contas/atual", access_token=tk["access_token"]))
    assert r.status_code == 401 and "outro aparelho" in r.json()["detail"]


def test_prova_capturada_nao_pode_ser_reenviada(cliente):
    p = Pessoa(cliente, "p@ex.com")
    chave = Chave()
    tk = _entrar(cliente, p, chave)
    prova = chave.prova("GET", "/contas/atual", access_token=tk["access_token"])
    assert _get(cliente, "/contas/atual", tk, p, prova).status_code == 200
    r = _get(cliente, "/contas/atual", tk, p, prova)
    assert r.status_code == 401 and "reutilizada" in r.json()["detail"]


def test_prova_de_outro_endereco_metodo_ou_horario(cliente):
    from app.core import tempo

    p = Pessoa(cliente, "p@ex.com")
    chave = Chave()
    tk = _entrar(cliente, p, chave)
    at = tk["access_token"]
    assert _get(cliente, "/contas/atual", tk, p, chave.prova("GET", "/pagamentos/transacoes", access_token=at)).status_code == 401
    assert _get(cliente, "/contas/atual", tk, p, chave.prova("POST", "/contas/atual", access_token=at)).status_code == 401
    velha = chave.prova("GET", "/contas/atual", access_token=at, iat=tempo.agora().timestamp() - 600)
    assert _get(cliente, "/contas/atual", tk, p, velha).status_code == 401
    # prova feita para OUTRO access token (ath não bate)
    assert _get(cliente, "/contas/atual", tk, p, chave.prova("GET", "/contas/atual", access_token="x" * 40)).status_code == 401


def test_prova_com_chave_privada_no_cabecalho_ou_alg_none(cliente):
    p = Pessoa(cliente, "p@ex.com")
    chave = Chave()
    tk = _entrar(cliente, p, chave)
    jwk_vazada = {**chave.jwk, "d": "AAAA"}
    r = _get(cliente, "/contas/atual", tk, p,
             chave.prova("GET", "/contas/atual", access_token=tk["access_token"], jwk=jwk_vazada))
    assert r.status_code == 401
    sem_assinatura = jwt.encode({"jti": "abcdefgh12", "htm": "GET", "htu": "/contas/atual", "iat": 0}, None,
                                algorithm="none", headers={"typ": "dpop+jwt", "jwk": chave.jwk})
    assert _get(cliente, "/contas/atual", tk, p, sem_assinatura).status_code == 401


def test_etapa_do_rosto_com_outra_chave_e_recusada(cliente):
    p = Pessoa(cliente, "p@ex.com")
    h = {"X-Dispositivo-Id": p.dispositivo}
    e = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA},
                     headers={**h, "DPoP": Chave().prova("POST", "/auth/login")}).json()
    r = cliente.post("/auth/login/mfa", headers={**h, "DPoP": Chave().prova("POST", "/auth/login/mfa")}, json={
        "mfa_token": e["mfa_token"], "biometria": {"desafio_id": e["desafio"]["desafio_id"], "quadros": QUADROS}})
    assert r.status_code == 401 and "mesma chave" in r.json()["detail"]


def test_refresh_roubado_nao_renova_sem_a_chave(cliente):
    p = Pessoa(cliente, "p@ex.com")
    chave = Chave()
    tk = _entrar(cliente, p, chave)
    h = {"X-Dispositivo-Id": p.dispositivo}
    corpo = {"refresh_token": tk["refresh_token"]}
    assert cliente.post("/auth/refresh", json=corpo, headers=h).status_code == 401
    assert cliente.post("/auth/refresh", json=corpo,
                        headers={**h, "DPoP": Chave().prova("POST", "/auth/refresh")}).status_code == 401
    r = cliente.post("/auth/refresh", json=corpo, headers={**h, "DPoP": chave.prova("POST", "/auth/refresh")})
    assert r.status_code == 200, r.text
    # o token novo continua amarrado à mesma chave
    novo = r.json()
    assert _get(cliente, "/contas/atual", novo, p,
                chave.prova("GET", "/contas/atual", access_token=novo["access_token"])).status_code == 200


def test_sessao_antiga_sem_chave_cai_quando_dpop_e_obrigatorio(cliente, monkeypatch):
    from app.core.config import get_settings

    p = Pessoa(cliente, "p@ex.com")  # login sem DPoP (modo desligado dos testes)
    assert cliente.get("/contas/atual", headers=p.h()).status_code == 200
    monkeypatch.setattr(get_settings(), "dpop_obrigatorio", True)
    r = cliente.get("/contas/atual", headers=p.h())
    assert r.status_code == 401 and "Entre de novo" in r.json()["detail"]


def test_producao_nao_sobe_sem_dpop(monkeypatch):
    from app.core import config

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("DPOP_OBRIGATORIO", "0")
    monkeypatch.setenv("BIOMETRIA_STUB", "0")
    monkeypatch.setenv("CNPJ_PROVEDOR", "brasilapi")
    monkeypatch.setenv("DOCUMENTO_PROVEDOR", "auto")
    monkeypatch.setenv("KYC_DOCUMENTO_OBRIGATORIO", "1")
    monkeypatch.setenv("DEPOSITO_DEMO", "0")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DPOP_OBRIGATORIO"):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()
