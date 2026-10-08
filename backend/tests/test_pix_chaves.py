"""Chaves Pix de ponta a ponta: cadastrar cada tipo, consultar e pagar entre contas diferentes."""

from tests.helpers import Pessoa, depositar


def _criar(cliente, p, tipo, valor=None, conta=None):
    corpo = {"tipo": tipo} if valor is None else {"tipo": tipo, "valor": valor}
    return cliente.post("/pix/chaves", json=corpo, headers=p.h(conta))


def test_cadastra_cada_tipo_de_chave_pf(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com")
    assert _criar(cliente, ana, "cpf").status_code == 201
    assert _criar(cliente, ana, "email", "Ana@Exemplo.com").status_code == 201
    assert _criar(cliente, ana, "celular", "(11) 98765-4321").status_code == 201
    assert _criar(cliente, ana, "aleatoria").status_code == 201
    chaves = cliente.get("/pix/chaves", headers=ana.h()).json()
    por_tipo = {k["tipo"]: k["valor"] for k in chaves}
    assert por_tipo["cpf"] == ana.cpf
    assert por_tipo["email"] == "ana@exemplo.com"
    assert por_tipo["celular"] == "+5511987654321"
    assert len(por_tipo["aleatoria"]) == 36


def test_chave_invalida_duplicada_e_limite(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com")
    bia = Pessoa(cliente, "bia@exemplo.com")
    assert _criar(cliente, ana, "email").status_code == 400  # sem o e-mail
    assert _criar(cliente, ana, "celular", "123").status_code == 400
    assert _criar(cliente, ana, "cnpj").status_code == 400  # conta pessoal
    assert _criar(cliente, ana, "email", "x@exemplo.com").status_code == 201
    assert _criar(cliente, ana, "email", "x@exemplo.com").status_code == 409
    assert _criar(cliente, bia, "email", "x@exemplo.com").status_code == 409  # já é de outra conta
    for _ in range(4):
        assert _criar(cliente, ana, "aleatoria").status_code == 201
    assert _criar(cliente, ana, "aleatoria").status_code == 400  # 5 por conta PF


def test_consulta_e_paga_por_cada_tipo_de_chave(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com", nome="Ana Souza")
    bia = Pessoa(cliente, "bia@exemplo.com", nome="Beatriz Lima")
    depositar(cliente, ana.numero, "1000.00")
    _criar(cliente, bia, "cpf")
    _criar(cliente, bia, "email", "bia.pix@exemplo.com")
    _criar(cliente, bia, "celular", "21999998888")
    aleatoria = _criar(cliente, bia, "aleatoria").json()["valor"]

    formas = [bia.cpf, f"{bia.cpf[:3]}.{bia.cpf[3:6]}.{bia.cpf[6:9]}-{bia.cpf[9:]}",
              "BIA.PIX@exemplo.com", "(21) 99999-8888", "+55 21 99999-8888", aleatoria]
    for chave in formas:
        r = cliente.get(f"/pix/consultar/{chave}", headers=ana.h())
        assert r.status_code == 200, (chave, r.text)
        assert r.json()["titular_tipo"] == "PF"
        assert r.json()["nome"].startswith("Beatriz")
        t = ana.transferir({"chave": chave}, "10.00")
        assert t.status_code == 200, (chave, t.text)
    assert bia.saldo() == "60.00"
    assert ana.saldo() == "940.00"


def test_chave_inexistente_e_pagar_a_si_mesmo(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com")
    depositar(cliente, ana.numero, "100.00")
    assert cliente.get("/pix/consultar/ninguem@exemplo.com", headers=ana.h()).status_code == 404
    assert ana.transferir({"chave": "ninguem@exemplo.com"}, "1.00").status_code == 404
    _criar(cliente, ana, "email", "ana.pix@exemplo.com")
    assert ana.transferir({"chave": "ana.pix@exemplo.com"}, "1.00").status_code == 400


def test_chaves_de_empresa_e_pix_entre_pf_e_pj(cliente):
    dono = Pessoa(cliente, "dono@exemplo.com")
    cli = Pessoa(cliente, "cliente@exemplo.com")
    pj = dono.abrir_empresa()["numero"]
    r = _criar(cliente, dono, "cnpj", conta=pj)
    assert r.status_code == 201, r.text
    cnpj = r.json()["valor"]
    assert _criar(cliente, dono, "cpf", conta=pj).status_code == 400  # CPF não vale na PJ
    assert _criar(cliente, dono, "email", "financeiro@empresa.com", conta=pj).status_code == 201
    # As chaves são da conta: a PF do dono não enxerga as da empresa.
    assert cliente.get("/pix/chaves", headers=dono.h()).json() == []
    assert len(cliente.get("/pix/chaves", headers=dono.h(pj)).json()) == 2

    depositar(cliente, cli.numero, "500.00")
    q = cliente.get(f"/pix/consultar/{cnpj}", headers=cli.h()).json()
    assert q["titular_tipo"] == "PJ"
    assert cli.transferir({"chave": "financeiro@empresa.com"}, "50.00").status_code == 200
    assert cli.transferir({"chave": cnpj}, "50.00").status_code == 200
    assert dono.saldo(pj) == "100.00"  # transferência não tem split

    _criar(cliente, cli, "email", "cliente.pix@exemplo.com")
    assert dono.transferir({"chave": "cliente.pix@exemplo.com"}, "30.00", conta=pj).status_code == 200
    assert cli.saldo() == "430.00"


def test_remover_chave_libera_para_outra_conta(cliente):
    ana = Pessoa(cliente, "ana@exemplo.com")
    bia = Pessoa(cliente, "bia@exemplo.com")
    k = _criar(cliente, ana, "email", "troca@exemplo.com").json()
    assert cliente.delete(f"/pix/chaves/{k['id']}", headers=bia.h()).status_code == 404  # não é dela
    assert cliente.delete(f"/pix/chaves/{k['id']}", headers=ana.h()).status_code == 204
    assert _criar(cliente, bia, "email", "troca@exemplo.com").status_code == 201
    assert cliente.get("/pix/consultar/troca@exemplo.com", headers=ana.h()).json()["nome"].startswith("Bia")


def test_eu_devolve_os_dados_de_quem_se_cadastrou(cliente):
    ana = Pessoa(cliente, "ana.real@exemplo.com", nome="Ana Real")
    eu = cliente.get("/auth/eu", headers=ana.h()).json()
    assert eu["email"] == "ana.real@exemplo.com"
    assert eu["nome"] == "Ana Real"
    [pf] = [c for c in eu["contas"] if c["titular_tipo"] == "PF"]
    assert pf["documento"] == ana.cpf
