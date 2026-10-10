from datetime import timedelta

from tests.helpers import QUADROS, SENHA, Pessoa, desafio, desconfiar_aparelho, gerar_cpf, login, login_completo, prova


def test_cadastro_cria_conta_pf_com_saldo_zero(cliente):
    p = Pessoa(cliente, "alef@ex.com")
    assert p.conta["saldo"] == "0.00"
    assert p.conta["titular_tipo"] == "PF"
    assert p.conta["agencia"] == "0001" and "-" in p.numero


def test_cadastro_exige_cpf_valido(cliente):
    r = cliente.post("/usuarios", json={"nome": "Xavier Lima", "email": "x@ex.com", "senha": SENHA, "cpf": "12345678900",
                                        "biometria": prova(cliente)})
    assert r.status_code == 400


def test_cpf_duplicado(cliente):
    p = Pessoa(cliente, "a@ex.com")
    r = cliente.post("/usuarios", json={"nome": "Bruna Lima", "email": "b@ex.com", "senha": SENHA, "cpf": p.cpf,
                                        "biometria": prova(cliente)})
    assert r.status_code == 409


def test_desafio_de_biometria_vale_uma_vez(cliente):
    d = desafio(cliente)
    corpo = {"nome": "Ana Lima", "email": "a@ex.com", "senha": SENHA, "cpf": gerar_cpf(),
             "biometria": {"desafio_id": d, "quadros": QUADROS}}
    assert cliente.post("/usuarios", json=corpo).status_code == 201
    corpo.update(email="b@ex.com", cpf=gerar_cpf())
    assert cliente.post("/usuarios", json=corpo).status_code == 401


def test_desafio_expirado(cliente, relogio):
    from app.core import tempo

    d = desafio(cliente)
    relogio.definir(tempo.agora() + timedelta(minutes=10))
    r = cliente.post("/usuarios", json={"nome": "Ana Lima", "email": "a@ex.com", "senha": SENHA, "cpf": gerar_cpf(),
                                        "biometria": {"desafio_id": d, "quadros": QUADROS}})
    assert r.status_code == 401 and "expirado" in r.json()["detail"]


def test_desafio_de_outra_pessoa_nao_serve(cliente):
    a = Pessoa(cliente, "a@ex.com")
    b = Pessoa(cliente, "b@ex.com")
    desconfiar_aparelho(b.dispositivo)
    # b confirma o aparelho com um desafio pedido pela sessão de a
    r = cliente.post("/seguranca/dispositivos/atual/confiar", json=a.prova(), headers=b.h())
    assert r.status_code == 401
    # e um desafio anônimo (de cadastro) também não serve para MFA
    r = cliente.post("/seguranca/dispositivos/atual/confiar", json=prova(cliente), headers=b.h())
    assert r.status_code == 401


def test_login_refresh_e_reuso(cliente):
    p = Pessoa(cliente, "alef@ex.com")
    h = {"X-Dispositivo-Id": p.dispositivo}
    tk = login_completo(cliente, "alef@ex.com", SENHA, p.dispositivo)
    # refresh preso ao aparelho da sessão
    assert cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]},
                        headers={"X-Dispositivo-Id": "outro"}).status_code == 401
    r1 = cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]}, headers=h)
    assert r1.status_code == 200
    # reuso do refresh antigo revoga a família inteira
    assert cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]}, headers=h).status_code == 401
    assert cliente.post("/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]}, headers=h).status_code == 401


def test_login_bloqueia_por_ip(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "login_max_tentativas_ip", 3)
    for i in range(3):
        assert cliente.post("/auth/login", json={"email": f"u{i}@ex.com", "senha": "x"}).status_code == 401
    assert cliente.post("/auth/login", json={"email": "outro@ex.com", "senha": "x"}).status_code == 429


def test_ip_atras_de_proxy(cliente, monkeypatch):
    from starlette.requests import Request

    from app.core.config import get_settings
    from app.deps import ip_cliente

    def req(cliente_ip, xff):
        return Request({"type": "http", "client": (cliente_ip, 1), "headers": [(b"x-forwarded-for", xff.encode())]})

    # sem proxy confiável, o header é ignorado (cliente não forja IP)
    assert ip_cliente(req("9.9.9.9", "1.2.3.4")) == "9.9.9.9"
    monkeypatch.setattr(get_settings(), "proxies_confiaveis", "10.0.0.1")
    assert ip_cliente(req("10.0.0.1", "1.2.3.4, 10.0.0.1")) == "1.2.3.4"
    # faixa CIDR (sub-rede do Container Apps): o proxy de entrada muda de IP
    monkeypatch.setattr(get_settings(), "proxies_confiaveis", "10.20.0.0/23")
    assert ip_cliente(req("10.20.1.7", "forjado, 1.2.3.4")) == "1.2.3.4"
    assert ip_cliente(req("10.20.2.1", "1.2.3.4")) == "10.20.2.1"
    # lixo no header não vira "IP"
    assert ip_cliente(req("10.20.1.7", "nao-e-ip")) == "10.20.1.7"


def test_ip_atras_do_front_door(cliente, monkeypatch):
    from starlette.requests import Request

    from app.core.config import get_settings
    from app.deps import ip_cliente

    def req(cabecalhos):
        h = [(k.encode(), v.encode()) for k, v in cabecalhos.items()]
        return Request({"type": "http", "client": ("10.20.0.9", 1), "headers": h})

    fd = {"x-azure-fdid": "id-do-perfil", "x-azure-clientip": "1.2.3.4"}
    # sem FRONT_DOOR_ID configurado, os headers do Front Door são ignorados
    assert ip_cliente(req(fd)) == "10.20.0.9"
    monkeypatch.setattr(get_settings(), "front_door_id", "id-do-perfil")
    # FDID conhecido não basta: sem proxy confiável o header é forjável.
    assert ip_cliente(req(fd)) == "10.20.0.9"
    monkeypatch.setattr(get_settings(), "proxies_confiaveis", "10.20.0.0/23")
    assert ip_cliente(req(fd)) == "1.2.3.4"
    # quem chama a origem direto e não sabe o id não escolhe o próprio IP
    assert ip_cliente(req({**fd, "x-azure-fdid": "chute"})) == "10.20.0.9"


def test_eu_lista_contas(cliente):
    p = Pessoa(cliente, "alef@ex.com")
    p.abrir_empresa()
    eu = cliente.get("/auth/eu", headers=p.h()).json()
    assert {c["titular_tipo"] for c in eu["contas"]} == {"PF", "PJ"}


def test_endpoint_protegido_sem_token(cliente):
    assert cliente.get("/contas/atual").status_code == 401


def test_login_usa_senha_certa(cliente):
    Pessoa(cliente, "alef@ex.com")
    assert cliente.post("/auth/login", json={"email": "alef@ex.com", "senha": "errada"}).status_code == 401
    assert login(cliente, "alef@ex.com", SENHA)
