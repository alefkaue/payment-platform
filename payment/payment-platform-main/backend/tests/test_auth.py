from tests.conftest import FOTO_FAKE


def _registrar(cliente, email="alef@ex.com", senha="senha12345", carteira_id=101, tipo="PF"):
    return cliente.post(
        "/usuarios",
        json={
            "nome": "Alef", "email": email, "senha": senha, "tipo": tipo,
            "carteira_id": carteira_id, "foto_rosto_base64": FOTO_FAKE,
        },
    )


def test_registro_cria_conta_com_saldo_zero(cliente):
    r = _registrar(cliente)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["carteira_id"] == 101
    assert body["saldo"] == 0.0  # sem saldo grátis (item #2)
    assert body["tem_biometria"] is True


def test_login_devolve_access_e_refresh(cliente):
    _registrar(cliente)
    r = cliente.post("/auth/login", json={"email": "alef@ex.com", "senha": "senha12345"})
    assert r.status_code == 200, r.text
    tk = r.json()
    assert tk["access_token"] and tk["refresh_token"]
    assert tk["token_type"] == "bearer"


def test_login_senha_errada_401(cliente):
    _registrar(cliente)
    r = cliente.post("/auth/login", json={"email": "alef@ex.com", "senha": "errada"})
    assert r.status_code == 401


def test_endpoint_protegido_sem_token_401(cliente):
    assert cliente.get("/usuarios/eu").status_code == 401


def test_refresh_rotaciona_e_revoga_o_antigo(cliente):
    _registrar(cliente)
    tk = cliente.post("/auth/login", json={"email": "alef@ex.com", "senha": "senha12345"}).json()
    r1 = cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]})
    assert r1.status_code == 200
    novo = r1.json()
    # Reusar o refresh ANTIGO agora deve falhar (rotação) e derrubar a sessão.
    r2 = cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]})
    assert r2.status_code == 401
    # E o novo refresh, que acabou de ser emitido, também foi invalidado pela
    # detecção de reuso (revogou todos). Login de novo resolve.
    r3 = cliente.post("/auth/refresh", json={"refresh_token": novo["refresh_token"]})
    assert r3.status_code == 401


def test_email_duplicado_409(cliente):
    _registrar(cliente)
    r = _registrar(cliente, carteira_id=102)  # mesmo e-mail, carteira diferente
    assert r.status_code == 409
