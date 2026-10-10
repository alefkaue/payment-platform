from tests.helpers import QUADROS, SENHA, Pessoa, depositar


def test_catalogo_da_loja_e_dos_voos(cliente):
    p = Pessoa(cliente, "p@ex.com")
    produtos = cliente.get("/loja/produtos", headers=p.h()).json()
    voos = cliente.get("/viagens/voos", headers=p.h()).json()
    assert len(produtos) == 8 and produtos[0]["merchant_nome"] == "TechPonto"
    assert len(voos) == 6 and voos[0]["milhas"] == 9000
    assert len(cliente.get("/viagens/voos?origem=CGH", headers=p.h()).json()) == 1


def test_compra_na_loja_tem_split_da_nota_e_rende_pontos(cliente):
    p = Pessoa(cliente, "p@ex.com")
    depositar(cliente, p.numero, 500)
    r = cliente.post("/loja/produtos/2/comprar", json={}, headers=p.h())  # Tênis, R$ 299,00
    assert r.status_code == 200, r.text
    c = r.json()
    t = c["transacao"]
    # 2026: CBS 0,9% + IBS 0,1% da nota emitida pelo lojista
    assert (t["valor_bruto"], t["cbs"], t["ibs"], t["aplicou_split"]) == ("299.00", "2.69", "0.30", True)
    assert c["pontos_ganhos"] == 299 and c["saldo_pontos"] == 299
    assert p.saldo() == "201.00"
    assert cliente.get("/pontos", headers=p.h()).json()["movimentos"][0]["motivo"] == "compra_loja"


def test_compra_acima_de_500_pede_biometria(cliente):
    p = Pessoa(cliente, "p@ex.com")
    depositar(cliente, p.numero, 1000)
    r = cliente.post("/loja/produtos/6/comprar", json={}, headers=p.h())  # Smartwatch R$ 629
    assert r.status_code == 400
    r = cliente.post("/loja/produtos/6/comprar", json={"biometria": p.prova()}, headers=p.h())
    assert r.status_code == 200 and r.json()["transacao"]["auth_metodo"] == "selfie"


def test_passagem_em_reais_e_resgate_com_pontos(cliente):
    from app.repositories import get_repository

    p = Pessoa(cliente, "p@ex.com")
    depositar(cliente, p.numero, 400)
    r = cliente.post("/viagens/voos/2/comprar", json={}, headers=p.h())  # LATAM R$ 289
    assert r.status_code == 200 and r.json()["pontos_ganhos"] == 289
    # 289 pontos não pagam um voo de 8.000 pontos
    r = cliente.post("/viagens/voos/2/resgatar", headers=p.h())
    assert r.status_code == 400 and "Pontos insuficientes" in r.json()["detail"]
    uid = cliente.get("/auth/eu", headers=p.h()).json()["usuario_id"]
    get_repository().mover_pontos(usuario_id=uid, delta=8000, motivo="compra_loja", descricao="teste")
    r = cliente.post("/viagens/voos/2/resgatar", headers=p.h())
    assert r.status_code == 200, r.text
    assert r.json()["pontos_usados"] == 8000 and r.json()["saldo_pontos"] == 289
    assert p.saldo() == "111.00"  # resgate não mexe no saldo em reais


def test_pj_nao_compra_na_loja(cliente):
    p = Pessoa(cliente, "p@ex.com")
    pj = p.abrir_empresa()
    depositar(cliente, pj["numero"], 1000)
    assert cliente.post("/loja/produtos/1/comprar", json={}, headers=p.h(pj["numero"])).status_code == 403


def test_login_por_cpf(cliente):
    p = Pessoa(cliente, "p@ex.com")
    cpf_formatado = f"{p.cpf[:3]}.{p.cpf[3:6]}.{p.cpf[6:9]}-{p.cpf[9:]}"
    r = cliente.post("/auth/login", json={"email": cpf_formatado, "senha": SENHA})
    assert r.status_code == 200 and r.json()["mfa_requerido"] is True


def test_login_so_com_biometria_nao_existe_mais(cliente):
    # O rosto é o 2º fator: entrar só com ele foi removido na v9.
    Pessoa(cliente, "p@ex.com")
    d = cliente.post("/biometria/desafios", json={"login": "p@ex.com"}).json()["desafio_id"]
    r = cliente.post("/auth/login/biometria", json={"email": "p@ex.com", "biometria": {"desafio_id": d, "quadros": QUADROS}})
    assert r.status_code in (404, 405)


def test_beneficios_desligados_respondem_404(cliente, monkeypatch):
    """Padrão em produção/pentest: Loja, Viagens e pontos fora do ar (SEGURANCA.md item 6)."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "beneficios_habilitados", False)
    p = Pessoa(cliente, "p@ex.com")
    for caminho in ("/loja/produtos", "/viagens/voos", "/pontos"):
        assert cliente.get(caminho, headers=p.h()).status_code == 404, caminho
    assert cliente.post("/loja/produtos/1/comprar", json={}, headers=p.h()).status_code == 404
