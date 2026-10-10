import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from tests.helpers import Pessoa, admin_h, depositar, gerar_chave_nfe


def _empresa(cliente, regime="regular"):
    dono = Pessoa(cliente, "loja@ex.com")
    pj = dono.abrir_empresa(regime_apuracao=regime)
    cnpj = cliente.get("/empresas/atual", headers=dono.h(pj["numero"])).json()["cnpj"]
    return dono, pj["numero"], cnpj


def _cobrar(cliente, dono, n, **dados):
    r = cliente.post("/cobrancas", json=dados, headers=dono.h(n))
    assert r.status_code == 201, r.text
    return r.json()


def test_cobranca_com_nota_retem_cbs_e_ibs_da_nota(cliente):
    dono, n, cnpj = _empresa(cliente)
    cliente_pf = Pessoa(cliente, "cliente@ex.com")
    depositar(cliente, cliente_pf.numero, 1000)
    [c] = _cobrar(cliente, dono, n, valor="400.00", nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "3.60", "ibs": "0.40"})
    assert c["vai_reter_imposto"] is True

    vista = cliente.get(f"/cobrancas/{c['txid']}", headers=cliente_pf.h()).json()
    assert vista["recebedor_nome"] == "Autopeças Teste"
    r = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=cliente_pf.h())
    t = r.json()
    assert (t["cbs"], t["ibs"], t["liquido"], t["aplicou_split"]) == ("3.60", "0.40", "396.00", True)
    assert dono.saldo(n) == "396.00"
    trib = cliente.get("/empresas/atual/tributos", headers=dono.h(n)).json()
    assert trib["a_repassar"] == "4.00"
    # pagar de novo não duplica
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=cliente_pf.h()).status_code == 409


def test_cobranca_sem_nota_ou_simples_nao_retem(cliente):
    dono, n, cnpj = _empresa(cliente, regime="simples")
    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 500)
    [c] = _cobrar(cliente, dono, n, valor="100.00", nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "0.90", "ibs": "0.10"})
    assert c["vai_reter_imposto"] is False
    t = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h()).json()
    assert t["aplicou_split"] is False and t["liquido"] == "100.00"


def test_nota_de_outro_cnpj_ou_chave_invalida(cliente):
    from tests.helpers import gerar_cnpj

    dono, n, cnpj = _empresa(cliente)
    r = cliente.post("/cobrancas", json={"valor": "10", "nota_fiscal": {"chave": gerar_chave_nfe(gerar_cnpj()), "cbs": "0", "ibs": "0"}}, headers=dono.h(n))
    assert r.status_code == 400 and "outro CNPJ" in r.json()["detail"]
    chave = gerar_chave_nfe(cnpj)
    chave = chave[:-1] + str((int(chave[-1]) + 1) % 10)
    r = cliente.post("/cobrancas", json={"valor": "10", "nota_fiscal": {"chave": chave, "cbs": "0", "ibs": "0"}}, headers=dono.h(n))
    assert r.status_code == 400
    r = cliente.post("/cobrancas", json={"valor": "10", "nota_fiscal": {"chave": gerar_chave_nfe(cnpj), "cbs": "9", "ibs": "2"}}, headers=dono.h(n))
    assert r.status_code == 400


def test_cobranca_para_pagador_especifico(cliente):
    dono, n, _ = _empresa(cliente)
    certo, errado = Pessoa(cliente, "certo@ex.com"), Pessoa(cliente, "errado@ex.com")
    depositar(cliente, errado.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00", pagador_documento=certo.cpf)
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=errado.h()).status_code == 403


def test_parcelamento_divide_valor_e_imposto(cliente):
    dono, n, cnpj = _empresa(cliente)
    cs = _cobrar(cliente, dono, n, valor="100.00", parcelas=3, vencimento="2026-11-10",
                 nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "8.80", "ibs": "0.10"})
    assert [c["valor"] for c in cs] == ["33.33", "33.33", "33.34"]
    assert sum(float(c["cbs"]) for c in cs) == 8.80 and sum(float(c["ibs"]) for c in cs) == 0.10
    assert [c["vencimento"] for c in cs] == ["2026-11-10", "2026-12-10", "2027-01-10"]
    assert len({c["grupo_parcelamento"] for c in cs}) == 1


def test_estorno_antes_do_repasse_devolve_tudo(cliente):
    dono, n, cnpj = _empresa(cliente)
    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 1000)
    depositar(cliente, n, 50)
    [c] = _cobrar(cliente, dono, n, valor="200.00", nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "17.60", "ibs": "0.20"})
    cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h())
    r = cliente.post(f"/cobrancas/{c['txid']}/estornar", headers=dono.h(n))
    assert r.status_code == 200, r.text
    assert pf.saldo() == "1000.00" and dono.saldo(n) == "50.00"
    assert cliente.get("/empresas/atual/tributos", headers=dono.h(n)).json()["a_repassar"] == "0.00"
    assert cliente.get(f"/cobrancas/{c['txid']}", headers=pf.h()).json()["status"] == "estornada"


def test_repasse_d_mais_1_e_estorno_depois_vira_credito(cliente, relogio):
    dono, n, cnpj = _empresa(cliente)
    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 1000)
    dia1 = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    relogio.definir(dia1)
    [c] = _cobrar(cliente, dono, n, valor="200.00", nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "17.60", "ibs": "0.20"})
    cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h())
    adm = admin_h(cliente)
    # no mesmo dia nada é repassado (D+1)
    assert cliente.post("/admin/tributos/repassar", headers=adm).json()["total"] == "0.00"
    relogio.definir(dia1 + timedelta(days=1))
    rep = cliente.post("/admin/tributos/repassar", headers=adm).json()
    assert rep["total"] == "17.80" and rep["pernas"] == 2
    resumo = cliente.get("/admin/tributos/resumo", headers=adm).json()
    assert resumo["saldo_conta_tributos"] == "0.00" and resumo["cbs_repassado"] == "17.60"

    depositar(cliente, n, 100)
    assert cliente.post(f"/cobrancas/{c['txid']}/estornar", headers=dono.h(n)).status_code == 200
    assert pf.saldo() == "1000.00"
    assert dono.saldo(n) == "82.20"  # 182,20 + 100 - 200
    creditos = cliente.get("/empresas/atual/creditos", headers=dono.h(n)).json()
    assert {(x["tributo"], x["valor"], x["fonte"]) for x in creditos} == {("CBS", "17.60", "estorno"), ("IBS", "0.20", "estorno")}


def test_credito_declarado_entra_na_restituicao_prevista(cliente):
    dono, n, cnpj = _empresa(cliente)
    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 1000)
    [c] = _cobrar(cliente, dono, n, valor="500.00", nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "44.00", "ibs": "0.50"})
    cliente.post(f"/cobrancas/{c['txid']}/pagar", json={"biometria": pf.prova()}, headers=pf.h())
    cliente.post("/empresas/atual/creditos", json={"tributo": "CBS", "valor": "30.00"}, headers=dono.h(n))
    t = cliente.get("/empresas/atual/tributos", headers=dono.h(n)).json()
    assert t["restituicao_prevista"] == "30.00" and t["modo_split"] == "inteligente"


def test_pix_automatico(cliente, relogio, monkeypatch):
    from app.core.config import get_settings

    # O JWT usa o relógio real e a sessão é conferida no relógio simulado; o
    # teste pula 36 dias, então a sessão do admin precisa durar mais que isso.
    monkeypatch.setattr(get_settings(), "refresh_token_exp_dias", 90)
    dono, n, _ = _empresa(cliente)
    assinante = Pessoa(cliente, "assinante@ex.com")
    depositar(cliente, assinante.numero, 200)
    relogio.definir(datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))
    a = cliente.post("/pix-automatico/autorizacoes", headers=dono.h(n), json={
        "pagador": {"numero": assinante.numero}, "descricao": "Plano mensal", "valor_maximo": "50.00", "periodicidade": "mensal",
    }).json()
    assert a["status"] == "pendente"
    # sem aceite não dá para cobrar
    corpo = {"valor": "49.90", "vencimento": "2026-10-10"}
    assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", json=corpo, headers=dono.h(n)).status_code == 409
    assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/aceitar", headers=assinante.h()).json()["status"] == "ativa"
    assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", json={"valor": "60", "vencimento": "2026-10-10"}, headers=dono.h(n)).status_code == 400
    c = cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", json=corpo, headers=dono.h(n))
    assert c.status_code == 201
    # uma por mês
    assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", json={**corpo, "vencimento": "2026-10-20"}, headers=dono.h(n)).status_code == 409

    adm = admin_h(cliente)
    assert cliente.post("/admin/jobs/recorrencias", headers=adm).json()["pagas"] == 0  # ainda não venceu
    relogio.definir(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc))
    assert cliente.post("/admin/jobs/recorrencias", headers=adm).json()["pagas"] == 1
    assert assinante.saldo() == "150.10"
    t = cliente.get("/pagamentos/transacoes", headers=assinante.h()).json()[0]
    assert t["auth_metodo"] == "automatico"

    # pagador cancela: próximas cobranças abertas são canceladas
    cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", json={"valor": "10", "vencimento": "2026-11-10"}, headers=dono.h(n))
    assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cancelar", headers=assinante.h()).json()["status"] == "cancelada"
    relogio.definir(datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc))
    assert cliente.post("/admin/jobs/recorrencias", headers=adm).json()["pagas"] == 0


def test_webhook_assinado(cliente, monkeypatch):
    from app.services import webhook_service

    enviados = []
    monkeypatch.setattr(webhook_service, "_enviar", lambda url, corpo, headers: (enviados.append((url, corpo, headers)) or (True, "HTTP 200")))
    dono, n, _ = _empresa(cliente)
    w = cliente.post("/empresas/atual/webhooks", json={"url": "https://erp.exemplo.com/payflow", "eventos": ["cobranca.paga"]}, headers=dono.h(n)).json()
    assert cliente.post("/empresas/atual/webhooks", json={"url": "http://inseguro", "eventos": ["cobranca.paga"]}, headers=dono.h(n)).status_code == 422
    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h())
    assert cliente.post("/admin/jobs/webhooks", headers=admin_h(cliente)).json()["processadas"] == 1
    url, corpo, headers = enviados[0]
    esperado = "sha256=" + hmac.new(w["segredo"].encode(), corpo, hashlib.sha256).hexdigest()
    assert headers["X-PayFlow-Assinatura"] == esperado
    assert json.loads(corpo)["dados"]["txid"] == c["txid"]
    entregas = cliente.get("/empresas/atual/webhooks/entregas", headers=dono.h(n)).json()
    assert entregas[0]["status"] == "entregue"


def test_rendimento_diario(cliente, relogio):
    from app.services import rendimento_service

    pf = Pessoa(cliente, "c@ex.com")
    depositar(cliente, pf.numero, 10000)
    adm = admin_h(cliente)
    r = cliente.post("/admin/jobs/rendimento?data=2026-10-07", headers=adm).json()
    esperado = (rendimento_service.taxa_diaria() * 10000).quantize(__import__("decimal").Decimal("0.01"), rounding="ROUND_DOWN")
    assert r["carteiras"] == 1 and r["total"] == str(esperado)
    # idempotente no mesmo dia
    assert cliente.post("/admin/jobs/rendimento?data=2026-10-07", headers=adm).json()["carteiras"] == 0
    # fim de semana não rende
    assert cliente.post("/admin/jobs/rendimento?data=2026-10-10", headers=adm).status_code == 400
    assert pf.saldo() == str(10000 + esperado)


def test_simulador_de_split(cliente):
    r = cliente.get("/pagamentos/split/simular?valor=1000&ano=2027").json()
    assert r["ibs"] == "1.00" and r["estimativa"] is True
    assert len(cliente.get("/pagamentos/split/transicao").json()) == 8




def test_acoes_de_cobranca_aparecem_na_auditoria_da_empresa(cliente):
    """Antes, cobrança criada/cancelada não levava empresa_id e sumia da trilha da empresa."""
    dono, n, _ = _empresa(cliente)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    assert cliente.post(f"/cobrancas/{c['txid']}/cancelar", json={}, headers=dono.h(n)).status_code in (200, 204)
    acoes = [a["acao"] for a in cliente.get("/empresas/atual/auditoria", headers=dono.h(n)).json()]
    assert "cobranca_criada" in acoes and "cobranca_cancelada" in acoes


def test_mesma_nota_nao_vira_duas_cobrancas(cliente):
    """R1-39: a mesma NF-e em outra cobrança reteria o imposto da nota de novo."""
    dono, n, cnpj = _empresa(cliente)
    nota = {"chave": gerar_chave_nfe(cnpj), "cbs": "0.90", "ibs": "0.10"}
    assert len(_cobrar(cliente, dono, n, valor="100.00", nota_fiscal=nota, parcelas=2, vencimento="2026-11-10")) == 2
    r = cliente.post("/cobrancas", json={"valor": "100.00", "nota_fiscal": nota}, headers=dono.h(n))
    assert r.status_code == 409 and "nota fiscal" in r.json()["detail"]


def test_debito_automatico_respeita_o_limite_do_pagador(cliente, relogio, monkeypatch):
    """R1-16: o recebedor não passa do limite por transação que o pagador escolheu."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "refresh_token_exp_dias", 90)
    dono, n, _ = _empresa(cliente)
    pagador = Pessoa(cliente, "limitado@ex.com")
    depositar(cliente, pagador.numero, 5000)
    assert cliente.put("/seguranca/limites", json={"por_transacao": "100.00"}, headers=pagador.h()).status_code == 200
    a = cliente.post("/pix-automatico/autorizacoes", headers=dono.h(n), json={
        "pagador": {"numero": pagador.numero}, "descricao": "Plano", "valor_maximo": "1000.00",
        "periodicidade": "mensal"}).json()
    cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/aceitar", headers=pagador.h())
    r = cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", headers=dono.h(n),
                     json={"valor": "800.00", "vencimento": "2026-10-10"})
    assert r.status_code == 201, r.text
    relogio.definir(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc))
    r = cliente.post("/admin/jobs/recorrencias", headers=admin_h(cliente)).json()
    assert r["pagas"] == 0
    assert pagador.saldo() == "5000.00"
