from tests.conftest import FOTO_FAKE

ADMIN = {"email": "admin@payflow.com.br", "senha": "admin-teste-123"}


def _registrar(cliente, email, carteira_id, tipo="PF"):
    r = cliente.post(
        "/usuarios",
        json={"nome": email.split("@")[0], "email": email, "senha": "senha12345",
              "tipo": tipo, "carteira_id": carteira_id, "foto_rosto_base64": FOTO_FAKE},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _token(cliente, email, senha="senha12345"):
    r = cliente.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _depositar(cliente, carteira_id, valor):
    adm = _token(cliente, ADMIN["email"], ADMIN["senha"])
    r = cliente.post("/admin/depositar", json={"carteira_id": carteira_id, "valor": valor}, headers=_auth(adm))
    assert r.status_code == 200, r.text
    return r.json()


def test_deposito_credita_e_exige_admin(cliente):
    _registrar(cliente, "a@ex.com", 101)
    tok = _token(cliente, "a@ex.com")
    # usuário comum não pode depositar
    r = cliente.post("/admin/depositar", json={"carteira_id": 101, "valor": 100}, headers=_auth(tok))
    assert r.status_code == 403
    # admin pode
    _depositar(cliente, 101, 100)
    eu = cliente.get("/usuarios/eu", headers=_auth(tok)).json()
    assert eu["saldo"] == 100.0


def test_transferencia_pf_sem_imposto(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202, tipo="PF")
    _depositar(cliente, 101, 300)
    tok = _token(cliente, "a@ex.com")
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 202, "valor": 100}, headers=_auth(tok))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["aplicou_split"] is False
    assert t["liquido"] == 100.0 and t["imposto_total"] == 0.0
    assert t["auth_metodo"] == "senha"  # abaixo do limite facial


def test_transferencia_pj_retem_imposto_para_governo(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "loja@ex.com", 303, tipo="PJ")
    _depositar(cliente, 101, 300)
    tok = _token(cliente, "a@ex.com")
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 303, "valor": 100}, headers=_auth(tok))
    assert r.status_code == 200, r.text
    t = r.json()
    # 2026: CBS 0,9% + IBS 0,1% de 100 -> 0,90 + 0,10; líquido 99,00
    assert t["aplicou_split"] is True
    assert t["cbs"] == 0.90 and t["ibs"] == 0.10 and t["liquido"] == 99.0
    # Governo (tela de retenções) soma o imposto
    adm = _token(cliente, ADMIN["email"], ADMIN["senha"])
    ret = cliente.get("/admin/governo/retencoes", headers=_auth(adm)).json()
    assert ret["total"] == 1.0


def test_saldo_insuficiente(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    tok = _token(cliente, "a@ex.com")
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 202, "valor": 50}, headers=_auth(tok))
    assert r.status_code == 400 and "insuficiente" in r.json()["detail"].lower()


def test_so_transfere_da_propria_carteira(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    # b tenta, mas a origem é sempre a carteira do autenticado -> b transfere de 202,
    # não de 101. Então b não consegue mexer na carteira de a de forma alguma.
    _depositar(cliente, 202, 100)
    tok_b = _token(cliente, "b@ex.com")
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 101, "valor": 10}, headers=_auth(tok_b))
    assert r.status_code == 200  # b -> a, ok (sai da carteira de b)
    assert r.json()["origem_carteira_id"] == 202


def test_valor_acima_do_limite_exige_selfie(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    _depositar(cliente, 101, 1000)
    tok = _token(cliente, "a@ex.com")
    # 600 > 500 (limite) e sem foto -> 400 pedindo selfie
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 202, "valor": 600}, headers=_auth(tok))
    assert r.status_code == 400 and "selfie" in r.json()["detail"].lower()
    # com foto (biometria falsificada no conftest) -> ok, auth_metodo selfie
    r2 = cliente.post(
        "/pagamentos/transferir",
        json={"destino_carteira_id": 202, "valor": 600, "foto_verificacao_base64": FOTO_FAKE},
        headers=_auth(tok),
    )
    assert r2.status_code == 200 and r2.json()["auth_metodo"] == "selfie"


def test_idempotencia_nao_duplica(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    _depositar(cliente, 101, 300)
    tok = _token(cliente, "a@ex.com")
    body = {"destino_carteira_id": 202, "valor": 50, "idempotency_key": "abc-123"}
    r1 = cliente.post("/pagamentos/transferir", json=body, headers=_auth(tok))
    r2 = cliente.post("/pagamentos/transferir", json=body, headers=_auth(tok))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]  # mesma transação, não duplicou
    eu = cliente.get("/usuarios/eu", headers=_auth(tok)).json()
    assert eu["saldo"] == 250.0  # debitou só uma vez


def test_valor_com_mais_de_duas_casas_rejeitado(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    _depositar(cliente, 101, 300)
    tok = _token(cliente, "a@ex.com")
    r = cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 202, "valor": 0.001}, headers=_auth(tok))
    assert r.status_code == 422  # pydantic rejeita >2 casas (item #8)


def test_usuario_comum_so_ve_proprias_transacoes(cliente):
    _registrar(cliente, "a@ex.com", 101)
    _registrar(cliente, "b@ex.com", 202)
    _registrar(cliente, "c@ex.com", 303)
    _depositar(cliente, 101, 100)
    tok_a = _token(cliente, "a@ex.com")
    cliente.post("/pagamentos/transferir", json={"destino_carteira_id": 202, "valor": 10}, headers=_auth(tok_a))
    # c não participou de nenhuma transferência -> histórico vazio
    tok_c = _token(cliente, "c@ex.com")
    assert cliente.get("/pagamentos/transacoes", headers=_auth(tok_c)).json() == []
