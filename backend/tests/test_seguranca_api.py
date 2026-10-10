"""Controles de API da auditoria (SECURITY_AUDIT.md): SSRF em webhooks, idempotência,
teto de corpo, paginação, erros sem detalhe interno e entradas maliciosas."""

import socket

import pytest

from app.services import webhook_service
from tests.helpers import Pessoa, conta_ref, depositar

# ------------------------------------------------------------------ SSRF (A-04)


@pytest.mark.parametrize("url", [
    "http://erp.exemplo.com/x",           # sem TLS
    "https://localhost/x",
    "https://api.localhost/x",
    "https://127.0.0.1/x",
    "https://10.20.2.4/x",                # Postgres/ VNet
    "https://169.254.169.254/latest/",    # metadados da nuvem
    "https://[::1]/x",
    "https://[::ffff:10.0.0.1]/x",        # IPv4 interno disfarçado de IPv6
    "https://erp.exemplo.com:5432/x",     # porta de outro serviço
    "https://user:senha@erp.exemplo.com/",
    "https://servico.internal/x",
])
def test_webhook_recusa_destino_interno(url):
    with pytest.raises(webhook_service.DestinoRecusado):
        webhook_service.validar_url(url)


def test_webhook_aceita_destino_publico():
    assert webhook_service.validar_url("https://erp.exemplo.com/payflow") == ("erp.exemplo.com", 443)
    assert webhook_service.validar_url("https://8.8.8.8:8443/x") == ("8.8.8.8", 8443)


def test_nome_que_resolve_para_rede_interna_nao_recebe(monkeypatch):
    def falso(host, porta, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", porta)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", porta))]

    monkeypatch.setattr(socket, "getaddrinfo", falso)
    ok, resposta = webhook_service._enviar("https://rebind.exemplo.com/x", b"{}", {})
    assert not ok and resposta.startswith("recusado")


def test_cadastro_de_webhook_interno_da_400(cliente):
    dono = Pessoa(cliente, "dono@ex.com")
    n = dono.abrir_empresa()["numero"]
    r = cliente.post("/empresas/atual/webhooks", json={"url": "https://169.254.169.254/x", "eventos": ["cobranca.paga"]},
                     headers=dono.h(n))
    assert r.status_code == 400


# ------------------------------------------------------------------ idempotência (A-08)


def test_mesma_chave_repete_sem_duplicar_e_outra_operacao_da_409(cliente):
    a, b, c = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com"), Pessoa(cliente, "c@ex.com")
    depositar(cliente, a.numero, 1000)
    r1 = a.transferir(conta_ref(b.numero), 100, idempotency_key="pagto-0001")
    r2 = a.transferir(conta_ref(b.numero), 100, idempotency_key="pagto-0001")
    assert r1.status_code == r2.status_code == 200 and r1.json()["id"] == r2.json()["id"]
    assert a.saldo() == "900.00"
    # mesma chave, outro valor ou outro destino: não devolve a antiga como se fosse a nova
    assert a.transferir(conta_ref(b.numero), 150, idempotency_key="pagto-0001").status_code == 409
    assert a.transferir(conta_ref(c.numero), 100, idempotency_key="pagto-0001").status_code == 409
    assert a.saldo() == "900.00"


# ------------------------------------------------------------------ teto de corpo (A-07)


def test_corpo_grande_sem_content_length_e_recusado(cliente, monkeypatch):
    import app.main as main

    camada = main.app.middleware_stack
    while camada is not None and not isinstance(camada, main.LimiteDeCorpo):
        camada = getattr(camada, "app", None)
    assert camada is not None
    monkeypatch.setattr(camada, "limite", 1024)

    def pedacos():
        for _ in range(10):
            yield b"x" * 512

    r = cliente.post("/auth/login", content=pedacos(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


# ------------------------------------------------------------------ paginação (A-11)


@pytest.mark.parametrize("caminho", ["/seguranca/atividade?limite=100000", "/seguranca/atividade?limite=-1",
                                     "/pagamentos/transacoes?limite=5000"])
def test_listagem_tem_teto(cliente, caminho):
    p = Pessoa(cliente, "p@ex.com")
    assert cliente.get(caminho, headers=p.h()).status_code == 422


# ------------------------------------------------------------------ erros e entradas maliciosas


def test_erro_interno_nao_vaza_detalhe(cliente, monkeypatch):
    def explode(*a, **kw):
        raise RuntimeError("postgresql://astroadmin:SENHA@10.20.2.4/astro C:\\app\\segredo.py")

    p = Pessoa(cliente, "p@ex.com")
    from app.repositories.repository import Repositorio

    monkeypatch.setattr(Repositorio, "contas_do_usuario", explode)
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app, raise_server_exceptions=False).get("/contas", headers=p.h())
    assert r.status_code == 500
    texto = r.text
    assert "SENHA" not in texto and "10.20.2.4" not in texto and "segredo.py" not in texto and "Traceback" not in texto
    assert r.json()["request_id"]


def test_validacao_nao_ecoa_o_valor_enviado(cliente):
    r = cliente.post("/auth/login", json={"email": "x", "senha": 123456789012345})
    assert r.status_code in (401, 422)
    assert "123456789012345" not in r.text


@pytest.mark.parametrize("payload", ["' OR '1'='1", "admin@ex.com' --", "\"; DROP TABLE usuarios; --"])
def test_sql_injection_no_login_nao_entra(cliente, payload):
    Pessoa(cliente, "admin2@ex.com")
    r = cliente.post("/auth/login", json={"email": payload, "senha": payload})
    assert r.status_code == 401
    # a tabela continua lá
    assert cliente.post("/auth/login", json={"email": "admin2@ex.com", "senha": "x"}).status_code == 401


def test_html_em_texto_livre_volta_como_texto_em_json(cliente):
    dono = Pessoa(cliente, "dono@ex.com")
    n = dono.abrir_empresa()["numero"]
    xss = "<img src=x onerror=alert(1)><script>alert(2)</script>"
    cob = cliente.post("/cobrancas", json={"valor": "10", "descricao": xss}, headers=dono.h(n))
    assert cob.status_code == 201
    r = cliente.get(f"/cobrancas/{cob.json()[0]['txid']}", headers=dono.h())
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.json()["descricao"] == xss  # guardado como dado; quem renderiza (React) escapa


def test_cors_nao_libera_origem_estranha_nem_credenciais(cliente):
    r = cliente.options("/auth/login", headers={"Origin": "https://golpe.exemplo.com",
                                                "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") != "https://golpe.exemplo.com"
    assert r.headers.get("access-control-allow-credentials") != "true"


# ------------------------------------------------------------------ logs (estruturados e à prova de injeção)


def test_log_json_tem_request_id_e_nao_deixa_forjar_linha():
    import json
    import logging

    from app.core import logs

    token = logs.request_id_atual.set("req-123456")
    try:
        registro = logging.makeLogRecord({"name": "astro.auditoria", "levelname": "INFO", "levelno": 20,
                                          "msg": "login_falhou\n{\"nivel\": \"INFO\", \"msg\": \"forjado\"}",
                                          "evento": "login"})
        linha = logs.FormatoJson().format(registro)
    finally:
        logs.request_id_atual.reset(token)
    assert "\n" not in linha  # uma linha só, por mais que a mensagem tenha quebra
    dados = json.loads(linha)
    assert dados["request_id"] == "req-123456" and dados["evento"] == "login"


def test_falha_na_trilha_nao_derruba_o_pix_ja_feito(cliente, monkeypatch):
    from app.db import models

    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 100)

    class Quebrada:
        def __init__(self, *args, **kw):
            raise RuntimeError("banco da auditoria fora do ar")

    monkeypatch.setattr("app.repositories.repository.LogAuditoria", Quebrada)
    r = a.transferir(conta_ref(b.numero), 10, idempotency_key="pix-com-trilha-quebrada")
    assert r.status_code == 200, r.text
    assert a.saldo() == "90.00" and b.saldo() == "10.00"
    assert models.LogAuditoria is not Quebrada
