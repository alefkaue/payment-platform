"""Autorização por objeto (IDOR/BOLA): um usuário não lê, altera nem apaga recurso de
outro trocando o id na URL ou o X-Conta. Cada recurso é criado pela VÍTIMA e o
ATACANTE (conta própria, empresa própria) tenta usá-lo."""

import pytest

from tests.helpers import Pessoa, admin_h, conta_ref, depositar
from tests.test_v9_seguranca import _aceitar, _convidar


@pytest.fixture()
def cenario(cliente):
    vit, atk, terc = Pessoa(cliente, "vitima@ex.com"), Pessoa(cliente, "atacante@ex.com"), Pessoa(cliente, "terceiro@ex.com")
    depositar(cliente, vit.numero, 5000)
    t = vit.transferir(conta_ref(terc.numero), 100).json()
    sessao = cliente.get("/auth/sessoes", headers=vit.h()).json()[0]
    disp = cliente.get("/seguranca/dispositivos", headers=vit.h()).json()[0]
    chave = cliente.post("/pix/chaves", json={"tipo": "aleatoria"}, headers=vit.h()).json()

    pj_v = vit.abrir_empresa()["numero"]
    pj_a = atk.abrir_empresa()["numero"]
    depositar(cliente, pj_v, 50000)
    op = Pessoa(cliente, "op@ex.com")
    vinc = _convidar(cliente, vit, pj_v, op, "operador", alcada=10)
    _aceitar(cliente, op, vinc.json()["id"])
    pend = op.transferir(conta_ref(terc.numero), 500, conta=pj_v).json()
    web = cliente.post("/empresas/atual/webhooks", json={"url": "https://erp.exemplo.com/x", "eventos": ["cobranca.paga"]},
                       headers=vit.h(pj_v)).json()
    func = cliente.post("/empresas/atual/funcionarios", json={"nome": "Func Silva", "cpf": terc.cpf}, headers=vit.h(pj_v)).json()
    cob = cliente.post("/cobrancas", json={"valor": "10"}, headers=vit.h(pj_v)).json()[0]
    convite = _convidar(cliente, vit, pj_v, Pessoa(cliente, "convidado@ex.com"), "consulta").json()
    return dict(cliente=cliente, vit=vit, atk=atk, terc=terc, t=t, sessao=sessao, disp=disp, chave=chave, pj_v=pj_v,
                pj_a=pj_a, vinc=vinc.json(), pend=pend, web=web, func=func, cob=cob, convite=convite)


def test_ninguem_usa_recurso_de_outro(cenario):
    c = cenario
    cli, atk, pa = c["cliente"], c["atk"], c["pj_a"]
    tentativas = {
        "ver transacao": cli.get(f"/pagamentos/transacoes/{c['t']['id']}", headers=atk.h()),
        "contestar transacao": cli.post(f"/pagamentos/transacoes/{c['t']['id']}/contestar", json={"motivo": "golpe golpe"}, headers=atk.h()),
        "encerrar sessao": cli.delete(f"/auth/sessoes/{c['sessao']['sessao_id']}", headers=atk.h()),
        "apagar aparelho": cli.delete(f"/seguranca/dispositivos/{c['disp']['id']}", headers=atk.h()),
        "bloquear aparelho": cli.post(f"/seguranca/dispositivos/{c['disp']['id']}/bloquear", json={}, headers=atk.h()),
        "apagar chave pix": cli.delete(f"/pix/chaves/{c['chave']['id']}", headers=atk.h()),
        "operar PJ alheia (X-Conta)": cli.get("/contas/atual", headers=atk.h(c["pj_v"])),
        "alterar vinculo alheio": cli.patch(f"/empresas/atual/vinculos/{c['vinc']['id']}", json={"alcada": "999999"}, headers=atk.h(pa)),
        "suspender vinculo alheio": cli.post(f"/empresas/atual/vinculos/{c['vinc']['id']}/suspender", json={}, headers=atk.h(pa)),
        "revogar vinculo alheio": cli.delete(f"/empresas/atual/vinculos/{c['vinc']['id']}", headers=atk.h(pa)),
        "decidir pendente alheia": cli.post(f"/pagamentos/pendentes/{c['pend']['operacao_id']}/decidir", json={"aprovar": False}, headers=atk.h(pa)),
        "apagar webhook alheio": cli.delete(f"/empresas/atual/webhooks/{c['web']['id']}", headers=atk.h(pa)),
        "apagar funcionario alheio": cli.delete(f"/empresas/atual/funcionarios/{c['func']['id']}", headers=atk.h(pa)),
        "cancelar cobranca alheia": cli.post(f"/cobrancas/{c['cob']['txid']}/cancelar", json={}, headers=atk.h(pa)),
        "estornar cobranca alheia": cli.post(f"/cobrancas/{c['cob']['txid']}/estornar", json={}, headers=atk.h(pa)),
        "aceitar convite alheio": cli.post(f"/convites/{c['convite']['id']}/aceitar", json={"biometria": atk.prova()}, headers=atk.h()),
        "recusar convite alheio": cli.post(f"/convites/{c['convite']['id']}/recusar", json={}, headers=atk.h()),
        "admin sem ser admin": cli.get("/admin/contas", headers=atk.h()),
        "deposito admin sem ser admin": cli.post("/admin/depositar", json={"destino": {"numero": atk.numero}, "valor": "100"}, headers=atk.h()),
    }
    passaram = {nome: r.status_code for nome, r in tentativas.items() if r.status_code not in (403, 404)}
    assert passaram == {}
    # nada mudou para a vítima
    assert c["vit"].saldo() == "4900.00"
    assert cli.get("/pix/chaves", headers=c["vit"].h()).json()
    assert cli.get("/empresas/atual/vinculos", headers=c["vit"].h(c["pj_v"])).json()


def test_sem_login_nada_protegido_responde(cliente):
    from app.core.rotas import todas_as_rotas
    from app.main import app

    publicas = {"/auth/login", "/auth/login/mfa", "/auth/login/mfa/desafio", "/auth/refresh", "/auth/logout",
                "/usuarios", "/biometria/desafios", "/pagamentos/split/simular", "/pagamentos/split/transicao", "/", "/saude"}
    rotas = todas_as_rotas(app)
    assert len(rotas) > 90  # se a lista vier curta, o teste passaria sem testar nada
    abertas = []
    for r in rotas:
        if r.path in publicas:
            continue
        caminho = r.path.replace("{", "").replace("}", "")  # ids viram texto: nem chega a validar
        for metodo in r.methods:
            st = cliente.request(metodo, caminho, json={}).status_code
            if st not in (401, 403):
                abertas.append((metodo, r.path, st))
    assert abertas == []


def test_quem_tem_o_txid_ve_a_cobranca_sem_dados_do_pagador(cenario):
    c = cenario
    cli = c["cliente"]
    pj_v, vit, atk = c["pj_v"], c["vit"], c["atk"]
    cob = cli.post("/cobrancas", json={"valor": "10", "pagador_documento": c["terc"].cpf}, headers=vit.h(pj_v)).json()[0]
    visto = cli.get(f"/cobrancas/{cob['txid']}", headers=atk.h()).json()
    assert visto["valor"] == "10.00" and visto["pagador_documento"] != c["terc"].cpf and "*" in visto["pagador_documento"]
    assert cli.get(f"/cobrancas/{cob['txid']}", headers=vit.h()).json()["pagador_documento"] == c["terc"].cpf
    assert cli.get(f"/cobrancas/{cob['txid']}", headers=c["terc"].h()).json()["pagador_documento"] == c["terc"].cpf
