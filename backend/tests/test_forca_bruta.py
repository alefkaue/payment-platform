"""Força bruta e enumeração (SEGURANCA.md item 4)."""

from tests.helpers import SENHA, Pessoa, gerar_cpf, prova_cadastro


def _cadastro(cliente, email, cpf):
    return cliente.post("/usuarios", json={"nome": "Pessoa Teste", "email": email, "senha": SENHA, "cpf": cpf,
                                           "biometria": prova_cadastro(cliente)})


def test_cadastro_tem_limite_por_ip(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "cadastro_max_ip_hora", 2)
    assert _cadastro(cliente, "a@ex.com", gerar_cpf()).status_code == 201
    assert _cadastro(cliente, "b@ex.com", gerar_cpf()).status_code == 201
    r = _cadastro(cliente, "c@ex.com", gerar_cpf())
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"


def test_cadastro_nao_diz_qual_dado_ja_existe(cliente):
    p = Pessoa(cliente, "a@ex.com")
    por_email = _cadastro(cliente, "a@ex.com", gerar_cpf())
    por_cpf = _cadastro(cliente, "outra@ex.com", p.cpf)
    assert por_email.status_code == por_cpf.status_code == 409
    assert por_email.json()["detail"] == por_cpf.json()["detail"]
    assert "e-mail" not in por_email.json()["detail"].split(".")[0]


def test_refresh_tem_limite_por_ip(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "refresh_max_ip_15min", 3)
    for _ in range(3):
        assert cliente.post("/auth/refresh", json={"refresh_token": "lixo"}).status_code == 401
    assert cliente.post("/auth/refresh", json={"refresh_token": "lixo"}).status_code == 429


def test_conta_bloqueia_mesmo_com_a_senha_certa_e_avisa_na_trilha(cliente):
    p = Pessoa(cliente, "p@ex.com")
    for _ in range(10):
        assert cliente.post("/auth/login", json={"email": p.email, "senha": "errada-123456"}).status_code == 401
    r = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA})
    assert r.status_code == 429 and "retry-after" in r.headers
    acoes = [e["acao"] for e in cliente.get("/seguranca/atividade", headers=p.h()).json()]
    assert "login_bloqueado_tentativas" in acoes


def test_login_inexistente_e_senha_errada_respondem_igual(cliente):
    Pessoa(cliente, "p@ex.com")
    a = cliente.post("/auth/login", json={"email": "p@ex.com", "senha": "errada-123456"})
    b = cliente.post("/auth/login", json={"email": "ninguem@ex.com", "senha": "errada-123456"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_atacante_nao_trava_a_conta_da_vitima_de_outro_ip(cliente, monkeypatch):
    """Erros de senha vindos de UM IP travam esse IP, não a conta (SECURITY_AUDIT.md A-06)."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "front_door_id", "fd")
    p = Pessoa(cliente, "p@ex.com")
    atacante = {"x-azure-fdid": "fd", "x-azure-clientip": "203.0.113.9"}
    vitima = {"x-azure-fdid": "fd", "x-azure-clientip": "198.51.100.7", "X-Dispositivo-Id": p.dispositivo}
    for _ in range(10):
        cliente.post("/auth/login", json={"email": p.email, "senha": "errada-123456"}, headers=atacante)
    assert cliente.post("/auth/login", json={"email": p.email, "senha": SENHA}, headers=atacante).status_code == 429
    assert cliente.post("/auth/login", json={"email": p.email, "senha": SENHA}, headers=vitima).status_code == 200


def test_ataque_distribuido_trava_a_conta(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "front_door_id", "fd")
    monkeypatch.setattr(get_settings(), "login_max_tentativas_conta", 12)
    p = Pessoa(cliente, "p@ex.com")
    for i in range(12):
        cliente.post("/auth/login", json={"email": p.email, "senha": "errada-123456"},
                     headers={"x-azure-fdid": "fd", "x-azure-clientip": f"203.0.113.{i + 1}"})
    r = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA},
                     headers={"x-azure-fdid": "fd", "x-azure-clientip": "198.51.100.7"})
    assert r.status_code == 429
