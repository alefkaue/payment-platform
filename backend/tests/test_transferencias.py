from datetime import datetime, timedelta, timezone

from tests.helpers import SENHA, Pessoa, admin_h, conta_ref, depositar, desconfiar_aparelho, login



def test_transferencia_para_pj_nao_retem_imposto(cliente):
    """Bug da v6: qualquer Pix para PJ perdia CBS/IBS. Transferência não é operação tributada."""
    a = Pessoa(cliente, "a@ex.com")
    empresa = a.abrir_empresa()
    depositar(cliente, a.numero, 300)
    r = a.transferir(conta_ref(empresa["numero"]), "100.00")
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["aplicou_split"] is False and t["imposto_total"] == "0.00" and t["liquido"] == "100.00"


def test_dinheiro_volta_como_string(cliente):
    a = Pessoa(cliente, "a@ex.com")
    depositar(cliente, a.numero, "10.10")
    assert a.saldo() == "10.10"


def test_transferencia_por_chave_pix(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    assert cliente.post("/pix/chaves", json={"tipo": "email", "valor": "B@Ex.com"}, headers=b.h()).status_code == 201
    depositar(cliente, a.numero, 50)
    r = a.transferir({"chave": "b@ex.com"}, 20)
    assert r.status_code == 200 and r.json()["destino"]["numero"] == b.numero


def test_saldo_insuficiente(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    r = a.transferir(conta_ref(b.numero), 50)
    assert r.status_code == 400 and "insuficiente" in r.json()["detail"].lower()


def test_exige_identificador_do_aparelho(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 50)
    # Sem o header, o token (preso ao aparelho do login) não vale.
    r = cliente.post("/pagamentos/transferir", json={"destino": conta_ref(b.numero), "valor": "10"},
                     headers={"Authorization": f"Bearer {a.token}"})
    assert r.status_code == 401 and "aparelho" in r.json()["detail"]


def test_idempotencia_por_conta(cliente):
    a, b, c = (Pessoa(cliente, f"{x}@ex.com") for x in "abc")
    depositar(cliente, a.numero, 300)
    depositar(cliente, c.numero, 300)
    r1 = a.transferir(conta_ref(b.numero), 50, idempotency_key="k1")
    r2 = a.transferir(conta_ref(b.numero), 50, idempotency_key="k1")
    assert r1.json()["id"] == r2.json()["id"] and a.saldo() == "250.00"
    # Mesma chave usada por OUTRA pessoa não devolve a transação de a (bug da v6)
    r3 = c.transferir(conta_ref(b.numero), 30, idempotency_key="k1")
    assert r3.json()["id"] != r1.json()["id"] and c.saldo() == "270.00"


def test_acima_do_limite_facial_exige_biometria(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    r = a.transferir(conta_ref(b.numero), 600)
    assert r.status_code == 400 and "biometria" in r.json()["detail"]
    r = a.transferir(conta_ref(b.numero), 600, biometria=a.prova())
    assert r.status_code == 200 and r.json()["auth_metodo"] == "selfie"


def test_aparelho_novo_limita_200_por_transacao_e_1000_por_dia(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 5000)
    # O login com rosto já confia no aparelho; o limite vale para um aparelho
    # que perdeu a confiança (ex.: desbloqueado depois de roubo). Simula direto no banco.
    a.dispositivo = "celular-novo"
    a.token = login(cliente, "a@ex.com", SENHA, a.dispositivo)
    desconfiar_aparelho(a.dispositivo)
    r = a.transferir(conta_ref(b.numero), 250, dispositivo="celular-novo")
    assert r.status_code == 403 and "aparelho novo" in r.json()["detail"]
    for _ in range(5):
        assert a.transferir(conta_ref(b.numero), 200, dispositivo="celular-novo").status_code == 200
    r = a.transferir(conta_ref(b.numero), 1, dispositivo="celular-novo")
    assert r.status_code == 403 and "por dia" in r.json()["detail"]
    # Confirmando o aparelho com verificação facial, volta ao limite normal
    ok = cliente.post("/seguranca/dispositivos/atual/confiar", json=a.prova(), headers=a.h(dispositivo="celular-novo"))
    assert ok.status_code == 200 and ok.json()["confiavel"] is True
    assert a.transferir(conta_ref(b.numero), 300, dispositivo="celular-novo").status_code == 200


def test_limite_noturno(cliente, relogio):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 5000)
    relogio.definir(datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc))  # 23h em Brasília
    assert a.transferir(conta_ref(b.numero), 400).status_code == 200
    assert a.transferir(conta_ref(b.numero), 400).status_code == 200
    r = a.transferir(conta_ref(b.numero), 300)
    assert r.status_code == 403 and "noturno" in r.json()["detail"]
    relogio.definir(datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc))  # 10h: período diurno
    assert a.transferir(conta_ref(b.numero), 300).status_code == 200


def test_aumento_de_limite_so_vale_depois_da_carencia(cliente, relogio):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 20000)
    base = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    relogio.definir(base)
    r = cliente.put("/seguranca/limites", json={"por_transacao": "8000", "noturno": "500"}, headers=a.h())
    lim = r.json()
    assert lim["noturno"] == "500.00"  # redução: na hora
    assert lim["por_transacao"] == "5000.00" and lim["pendente"]["por_transacao"] == "8000.00"
    assert a.transferir(conta_ref(b.numero), 6000, biometria=a.prova()).status_code == 403
    relogio.definir(base + timedelta(hours=25))
    assert a.transferir(conta_ref(b.numero), 6000, biometria=a.prova()).status_code == 200


def test_bloqueio_cautelar_e_contestacao_procedente(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 5000)
    r = a.transferir(conta_ref(b.numero), 1500, biometria=a.prova())
    t = r.json()
    assert t["status"] == "retida"
    conta_b = cliente.get("/contas/atual", headers=b.h()).json()
    assert conta_b["saldo"] == "0.00" and conta_b["saldo_bloqueado"] == "1500.00"
    # b não consegue gastar o valor retido
    assert b.transferir(conta_ref(a.numero), 10).status_code == 400

    c = cliente.post(f"/pagamentos/transacoes/{t['id']}/contestar", json={"motivo": "Caí num golpe"}, headers=a.h())
    assert c.status_code == 201
    d = cliente.post(f"/admin/contestacoes/{c.json()['id']}/decidir", json={"procedente": True}, headers=admin_h(cliente))
    assert d.json()["status"] == "procedente" and d.json()["valor_devolvido"] == "1500.00"
    assert a.saldo() == "5000.00"
    assert cliente.get("/contas/atual", headers=b.h()).json()["saldo_bloqueado"] == "0.00"


def test_bloqueio_libera_sozinho_depois_do_prazo(cliente, relogio):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 5000)
    base = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    relogio.definir(base)
    t = a.transferir(conta_ref(b.numero), 1200, biometria=a.prova()).json()
    assert t["status"] == "retida"
    relogio.definir(base + timedelta(hours=73))
    assert cliente.post("/admin/jobs/liberar-bloqueios", headers=admin_h(cliente)).json()["liberadas"] == 1
    assert b.saldo() == "1200.00"
    # segunda transferência para o mesmo destino não é retida (já transacionaram)
    assert a.transferir(conta_ref(b.numero), 1200, biometria=a.prova()).json()["status"] == "concluida"


def test_contestacao_improcedente_libera(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 5000)
    t = a.transferir(conta_ref(b.numero), 1500, biometria=a.prova()).json()
    c = cliente.post(f"/pagamentos/transacoes/{t['id']}/contestar", json={"motivo": "Me arrependi"}, headers=a.h()).json()
    cliente.post(f"/admin/contestacoes/{c['id']}/decidir", json={"procedente": False}, headers=admin_h(cliente))
    assert b.saldo() == "1500.00"


def test_lote(cliente):
    a, b, c = (Pessoa(cliente, f"{x}@ex.com") for x in "abc")
    depositar(cliente, a.numero, 300)
    r = cliente.post("/pagamentos/lote", headers=a.h(), json={"itens": [
        {"destino": conta_ref(b.numero), "valor": "100"},
        {"destino": {"chave": "naoexiste@ex.com"}, "valor": "10"},
        {"destino": conta_ref(c.numero), "valor": "150"},
        {"destino": conta_ref(c.numero), "valor": "100"},
    ]})
    res = r.json()
    assert [x["situacao"] for x in res] == ["concluida", "erro", "concluida", "erro"]
    assert "insuficiente" in res[3]["erro"]


def test_lote_acima_do_limite_facial_pede_uma_biometria(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 2000)
    itens = [{"destino": conta_ref(b.numero), "valor": "300"}] * 2
    assert cliente.post("/pagamentos/lote", headers=a.h(), json={"itens": itens}).status_code == 400
    r = cliente.post("/pagamentos/lote", headers=a.h(), json={"itens": itens, "biometria": a.prova()})
    assert [x["situacao"] for x in r.json()] == ["concluida", "concluida"]


def test_extrato_so_da_propria_conta(cliente):
    a, b, c = (Pessoa(cliente, f"{x}@ex.com") for x in "abc")
    depositar(cliente, a.numero, 100)
    t = a.transferir(conta_ref(b.numero), 10).json()
    assert cliente.get("/pagamentos/transacoes", headers=c.h()).json() == []
    assert cliente.get(f"/pagamentos/transacoes/{t['id']}", headers=c.h()).status_code == 404


def test_valor_com_mais_de_duas_casas(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    assert a.transferir(conta_ref(b.numero), "0.001").status_code == 422
