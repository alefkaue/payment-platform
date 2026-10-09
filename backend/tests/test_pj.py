from tests.helpers import Pessoa, conta_ref, depositar


def _vincular(cliente, admin: Pessoa, numero_pj: str, pessoa: Pessoa, papel: str, alcada=None):
    """Admin convida pelo CPF (com o próprio rosto, exigido em papéis/alçadas
    sensíveis) e a pessoa aceita com o rosto dela."""
    corpo = {"cpf": pessoa.cpf, "nome": "Pessoa Convidada", "papel": papel, "biometria": admin.prova()}
    if alcada is not None:
        corpo["alcada"] = str(alcada)
    r = cliente.post("/empresas/atual/vinculos", json=corpo, headers=admin.h(numero_pj))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pendente"
    r = cliente.post(f"/convites/{r.json()['id']}/aceitar", json={"biometria": pessoa.prova()}, headers=pessoa.h())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ativo"
    return r.json()


def test_abrir_empresa(cliente):
    socia = Pessoa(cliente, "socia@ex.com")
    pj = socia.abrir_empresa(regime_apuracao="regular")
    assert pj["titular_tipo"] == "PJ" and pj["papel"] == "admin" and pj["saldo"] == "0.00"
    emp = cliente.get("/empresas/atual", headers=socia.h(pj["numero"])).json()
    assert emp["verificada_por"] == "stub" and emp["situacao_cadastral"] == "ATIVA"


def test_cnpj_invalido_e_duplicado(cliente):
    p = Pessoa(cliente, "p@ex.com")
    assert cliente.post("/empresas", json={"cnpj": "11.222.333/0001-82"}, headers=p.h()).status_code == 400
    pj = p.abrir_empresa()
    emp = cliente.get("/empresas/atual", headers=p.h(pj["numero"])).json()
    assert cliente.post("/empresas", json={"cnpj": emp["cnpj"]}, headers=p.h()).status_code == 409


def test_cnpj_sem_o_cpf_no_quadro_de_socios(cliente, monkeypatch):
    from app.services import cnpj_service

    def falso(cnpj):
        return cnpj_service.DadosCnpj(cnpj=cnpj, razao_social="X LTDA", nome_fantasia=None, situacao="ATIVA", cnae="4530703",
                                      socios=[cnpj_service.Socio(nome="OUTRA PESSOA", cpf_mascarado="***000000**")])

    monkeypatch.setitem(cnpj_service._PROVEDORES, "stub", falso)
    p = Pessoa(cliente, "p@ex.com")
    from tests.helpers import gerar_cnpj

    r = cliente.post("/empresas", json={"cnpj": gerar_cnpj()}, headers=p.h())
    assert r.status_code == 403 and "quadro de sócios" in r.json()["detail"]


def test_mei_vira_regime_mei(cliente):
    p = Pessoa(cliente, "p@ex.com")
    pj = p.abrir_empresa(porte="MEI", regime_apuracao="regular")
    assert pj["regime_apuracao"] == "mei"


def test_sem_vinculo_nao_opera_empresa(cliente):
    dono, estranho = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "x@ex.com")
    pj = dono.abrir_empresa()
    assert cliente.get("/contas/atual", headers=estranho.h(pj["numero"])).status_code == 403


def test_alcada_e_dupla_aprovacao(cliente):
    dono = Pessoa(cliente, "dono@ex.com")
    op = Pessoa(cliente, "operador@ex.com")
    aprov = Pessoa(cliente, "aprovador@ex.com")
    forn = Pessoa(cliente, "fornecedor@ex.com")
    pj = dono.abrir_empresa()
    n = pj["numero"]
    depositar(cliente, n, 10000)
    _vincular(cliente, dono, n, op, "operador", alcada=1000)
    _vincular(cliente, dono, n, aprov, "aprovador", alcada=5000)

    # dentro da alçada: executa direto
    assert op.transferir(conta_ref(forn.numero), 800, conta=n, biometria=op.prova()).status_code == 200
    # acima: 202 pendente, sem mexer no saldo
    r = op.transferir(conta_ref(forn.numero), 3000, conta=n)
    assert r.status_code == 202, r.text
    oid = r.json()["operacao_id"]
    assert dono.saldo(n) == "9200.00"
    # quem lançou não aprova
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": op.prova()}, headers=op.h(n))
    assert r.status_code == 403
    # aprovador aprova (com biometria, valor > limite facial) e executa
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": aprov.prova()}, headers=aprov.h(n))
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text
    assert dono.saldo(n) == "6200.00"
    # não dá para aprovar duas vezes
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": aprov.prova()}, headers=aprov.h(n))
    assert r.status_code == 409


def test_aprovador_nao_aprova_acima_da_propria_alcada(cliente):
    dono, op, aprov, forn = (Pessoa(cliente, f"{x}@ex.com") for x in ("dono", "op", "apr", "forn"))
    pj = dono.abrir_empresa()
    n = pj["numero"]
    depositar(cliente, n, 50000)
    _vincular(cliente, dono, n, op, "operador", alcada=100)
    _vincular(cliente, dono, n, aprov, "aprovador", alcada=1000)
    oid = op.transferir(conta_ref(forn.numero), 2000, conta=n).json()["operacao_id"]
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": aprov.prova()}, headers=aprov.h(n))
    assert r.status_code == 403
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": dono.prova()}, headers=dono.h(n))
    assert r.status_code == 200


def test_papel_consulta_nao_movimenta(cliente):
    dono, leitor, forn = (Pessoa(cliente, f"{x}@ex.com") for x in ("dono", "leitor", "forn"))
    pj = dono.abrir_empresa()
    depositar(cliente, pj["numero"], 1000)
    _vincular(cliente, dono, pj["numero"], leitor, "consulta")
    assert leitor.saldo(pj["numero"]) == "1000.00"
    assert leitor.transferir(conta_ref(forn.numero), 10, conta=pj["numero"]).status_code == 403


def test_empresa_nao_fica_sem_admin(cliente):
    dono = Pessoa(cliente, "dono@ex.com")
    pj = dono.abrir_empresa()
    vs = cliente.get("/empresas/atual/vinculos", headers=dono.h(pj["numero"])).json()
    r = cliente.delete(f"/empresas/atual/vinculos/{vs[0]['id']}", headers=dono.h(pj["numero"]))
    assert r.status_code == 400


def test_chaves_pix_e_consulta_mascarada(cliente):
    a, b = Pessoa(cliente, "a@ex.com", nome="Bianca Souza Lima"), Pessoa(cliente, "b@ex.com")
    assert cliente.post("/pix/chaves", json={"tipo": "cpf"}, headers=a.h()).status_code == 201
    assert cliente.post("/pix/chaves", json={"tipo": "cnpj"}, headers=a.h()).status_code == 400
    al = cliente.post("/pix/chaves", json={"tipo": "aleatoria"}, headers=a.h()).json()
    assert len(al["valor"]) == 36
    r = cliente.get(f"/pix/consultar/{a.cpf}", headers=b.h()).json()
    assert r["nome"] == "Bianca S*** L***" and r["documento"].startswith("***.")
    assert cliente.post("/pix/chaves", json={"tipo": "cpf"}, headers=a.h()).status_code == 409


def test_consulta_de_chave_tem_limite(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "consulta_chave_max_hora", 2)
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    cliente.post("/pix/chaves", json={"tipo": "cpf"}, headers=a.h())
    for _ in range(2):
        assert cliente.get(f"/pix/consultar/{a.cpf}", headers=b.h()).status_code == 200
    assert cliente.get(f"/pix/consultar/{a.cpf}", headers=b.h()).status_code == 429


def test_consulta_por_numero_de_conta_e_aparelho_atual(cliente):
    a, b = Pessoa(cliente, "a@ex.com", nome="Ana Paula Reis"), Pessoa(cliente, "b@ex.com")
    r = cliente.get(f"/pix/consultar/{a.numero}", headers=b.h()).json()
    assert r["nome"] == "Ana P*** R***"
    assert cliente.get("/seguranca/dispositivos/atual", headers=b.h()).json()["confiavel"] is True
    # o token está preso ao aparelho em que o login foi feito
    assert cliente.get("/seguranca/dispositivos/atual", headers=b.h(dispositivo="outro")).status_code == 401
