"""Ataques independentes C1; contas sintéticas, sem alteração do código da API."""
import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.helpers import Pessoa, SENHA, QUADROS, conta_ref, depositar, login_completo
from tests.test_v9_seguranca import _convidar, _aceitar


@pytest.mark.parametrize("ataque", ["none", "HS512", "RS256", "assinatura", "sub", "papel", "exp", "nbf", "iat", "aud", "iss"])
def test_adv_jwt_manipulado_nao_autentica(cliente, ataque):
    p = Pessoa(cliente, "jwt@ex.com")
    claims = jwt.decode(p.token, options={"verify_signature": False})
    header = jwt.get_unverified_header(p.token)
    if ataque in ("none", "HS512", "RS256"):
        chave = "" if ataque == "none" else (rsa.generate_private_key(public_exponent=65537, key_size=2048) if ataque == "RS256" else "chave-atacante-" * 8)
        token = jwt.encode(claims, chave, algorithm=ataque, headers={"typ": header["typ"]})
    elif ataque == "assinatura":
        partes = p.token.split(".")
        partes[2] = ("A" if partes[2][0] != "A" else "B") + partes[2][1:]
        token = ".".join(partes)
    else:
        claims[ataque] = {"sub": "999999", "papel": "admin", "exp": 1, "nbf": int(time.time()) + 3600,
                          "iat": int(time.time()) + 3600, "aud": "outro", "iss": "outro"}[ataque]
        partes = p.token.split(".")
        partes[1] = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        token = ".".join(partes)
    assert cliente.get("/auth/eu", headers={**p.h(), "Authorization": f"Bearer {token}"}).status_code == 401
    assert cliente.get("/admin/contas", headers=p.h()).status_code == 403


@pytest.mark.parametrize("claim,valor", [("exp", 1), ("nbf", 4102444800), ("iat", 4102444800), ("aud", "outro"), ("iss", "outro")])
def test_adv_claims_invalidas_mesmo_com_assinatura_valida(cliente, claim, valor):
    from app.core.config import get_settings
    p = Pessoa(cliente, "claims@ex.com")
    claims = jwt.decode(p.token, options={"verify_signature": False})
    claims[claim] = valor
    token = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256", headers={"typ": jwt.get_unverified_header(p.token)["typ"]})
    assert cliente.get("/auth/eu", headers={**p.h(), "Authorization": f"Bearer {token}"}).status_code == 401


def test_adv_tipos_de_token_nao_sao_intercambiaveis(cliente):
    p = Pessoa(cliente, "tipos@ex.com")
    completo = login_completo(cliente, p.email, SENHA, p.dispositivo)
    etapa = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA}, headers=p.h()).json()
    rec = cliente.post("/auth/recuperacao", json={"login": p.email, "data_nascimento": "1990-01-01"}, headers=p.h()).json()
    for token in (completo["refresh_token"], etapa["mfa_token"], rec["recuperacao_token"]):
        assert cliente.get("/auth/eu", headers={**p.h(), "Authorization": f"Bearer {token}"}).status_code == 401
    assert cliente.post("/auth/login/mfa", headers=p.h(), json={"mfa_token": rec["recuperacao_token"],
        "biometria": {"desafio_id": etapa["desafio"]["desafio_id"], "quadros": QUADROS}}).status_code == 401


@pytest.mark.parametrize("evento", ["logout", "encerrar", "bloquear", "reuso", "aparelho"])
def test_adv_access_e_refresh_de_sessao_invalidada(cliente, evento):
    p = Pessoa(cliente, "sessao@ex.com")
    tk = login_completo(cliente, p.email, SENHA, p.dispositivo)
    h = {**p.h(), "Authorization": f"Bearer {tk['access_token']}"}
    if evento == "logout":
        assert cliente.post("/auth/logout", json={"refresh_token": tk["refresh_token"]}, headers=h).status_code in (200, 204)
    elif evento == "encerrar":
        claims = jwt.decode(tk["access_token"], options={"verify_signature": False})
        sessoes = cliente.get("/auth/sessoes", headers=h).json()
        alvo = next(s for s in sessoes if s["sessao_id"] == claims["sid"])
        assert cliente.delete(f"/auth/sessoes/{alvo['sessao_id']}", headers=h).status_code in (200, 204)
    elif evento == "bloquear":
        d = cliente.get("/seguranca/dispositivos", headers=h).json()[0]
        assert cliente.post(f"/seguranca/dispositivos/{d['id']}/bloquear", headers=h).status_code in (200, 204)
    elif evento == "reuso":
        assert cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]}, headers=h).status_code == 200
        assert cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]}, headers=h).status_code == 401
    else:
        h["X-Dispositivo-Id"] = "aparelho-atacante"
    assert cliente.get("/auth/eu", headers=h).status_code == 401
    assert cliente.post("/auth/refresh", json={"refresh_token": tk["refresh_token"]}, headers=h).status_code == 401


@pytest.mark.parametrize("valor", ["0.001", "-0", 10.005, "999999999999999999999", "abc", None, "NaN", "Infinity", True, {}, []])
def test_adv_valores_invalidos_nao_movem_saldo(cliente, valor):
    a, b = Pessoa(cliente, "valor@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 100)
    r = cliente.post("/pagamentos/transferir", json={"destino": conta_ref(b.numero), "valor": valor}, headers=a.h())
    assert r.status_code in (400, 422), r.text
    assert a.saldo() == "100.00" and b.saldo() == "0.00"


@pytest.mark.parametrize("valor,esperado", [("  10 ", "10.00"), ("1e1", "10.00"), ("1e3", "1000.00"), ("10", "10.00")])
def test_adv_decimal_equivalente_preserva_valor(cliente, valor, esperado):
    a, b = Pessoa(cliente, "decimal@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 2000)
    r = a.transferir(conta_ref(b.numero), valor, biometria=a.prova())
    assert r.status_code == 200, r.text
    assert r.json()["valor_bruto"] == esperado


def test_adv_mass_assignment_transferencia_e_conta(cliente):
    a, b = Pessoa(cliente, "mass@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 100)
    r = cliente.post("/pagamentos/transferir", json={"destino": conta_ref(b.numero), "valor": "10", "saldo": "999999",
        "origem_carteira_id": b.conta["carteira_id"], "autor_id": "999999", "papel": "admin", "status": "aprovada",
        "cbs": "-100", "ibs": "-100", "liquido": "10000"}, headers=a.h())
    assert r.status_code == 200, r.text
    assert a.saldo() == "90.00" and b.saldo() == "10.00"
    assert r.json()["cbs"] == r.json()["ibs"] == "0.00"


@pytest.mark.parametrize("status", ["suspenso", "revogado"])
def test_adv_x_conta_de_vinculo_inativo(cliente, status):
    dono, op = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "op@ex.com")
    pj = dono.abrir_empresa()["numero"]
    v = _convidar(cliente, dono, pj, op, "consulta").json()
    _aceitar(cliente, op, v["id"])
    if status == "suspenso":
        r = cliente.post(f"/empresas/atual/vinculos/{v['id']}/suspender", headers=dono.h(pj))
    else:
        r = cliente.delete(f"/empresas/atual/vinculos/{v['id']}", headers=dono.h(pj))
    assert r.status_code in (200, 204)
    assert cliente.get("/contas/atual", headers=op.h(pj)).status_code in (403, 404)


@pytest.mark.parametrize("papel", ["consulta", "operador"])
def test_adv_papel_nao_admin_nao_gera_poder(cliente, papel):
    dono, op = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "op@ex.com")
    pj = dono.abrir_empresa()["numero"]
    v = _convidar(cliente, dono, pj, op, papel, **({"alcada": 100} if papel == "operador" else {})).json()
    _aceitar(cliente, op, v["id"])
    tentativas = [cliente.patch(f"/empresas/atual/vinculos/{v['id']}", json={"papel": "admin"}, headers=op.h(pj)),
        cliente.post("/empresas/atual/webhooks", json={"url": "https://exemplo.com/x", "eventos": ["cobranca.paga"]}, headers=op.h(pj)),
        cliente.post("/empresas/atual/funcionarios", json={"nome": "Pessoa", "cpf": dono.cpf}, headers=op.h(pj))]
    assert all(r.status_code == 403 for r in tentativas), [(r.status_code, r.text) for r in tentativas]


def test_adv_login_alias_e_headers_forjados_nao_driblam_limite(cliente):
    p = Pessoa(cliente, "alias@ex.com")
    cpf = p.cpf
    aliases = [p.email.upper(), "  " + p.email + "  ", cpf, f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"]
    for i in range(10):
        r = cliente.post("/auth/login", json={"email": aliases[i % 4], "senha": "incorreta"},
            headers={"X-Forwarded-For": f"203.0.113.{i + 1}", "X-Azure-ClientIP": f"198.51.100.{i + 1}"})
        assert r.status_code == 401
    for alias in aliases:
        assert cliente.post("/auth/login", json={"email": alias, "senha": SENHA}).status_code == 429


@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "DELETE"])
def test_adv_troca_metodo_nao_edita_transacao(cliente, metodo):
    a, b = Pessoa(cliente, "metodo@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 100)
    t = a.transferir(conta_ref(b.numero), 10).json()
    assert cliente.request(metodo, f"/pagamentos/transacoes/{t['id']}", json={"valor_bruto": "999"}, headers=a.h()).status_code == 405
    assert a.saldo() == "90.00" and b.saldo() == "10.00"


def test_adv_recebedor_nao_contesta_transacao(cliente):
    a, b = Pessoa(cliente, "med@ex.com"), Pessoa(cliente, "destino@ex.com")
    depositar(cliente, a.numero, 100)
    t = a.transferir(conta_ref(b.numero), 10).json()
    r = cliente.post(f"/pagamentos/transacoes/{t['id']}/contestar", json={"motivo": "Golpe de teste"}, headers=b.h())
    assert r.status_code in (400, 403, 404), r.text
    assert a.saldo() == "90.00" and b.saldo() == "10.00"


def test_adv_folha_funcionario_de_outra_empresa(cliente):
    a, b, f = Pessoa(cliente, "empresa@ex.com"), Pessoa(cliente, "outra@ex.com"), Pessoa(cliente, "func@ex.com")
    pa, pb = a.abrir_empresa()["numero"], b.abrir_empresa()["numero"]
    depositar(cliente, pa, 100)
    fid = cliente.post("/empresas/atual/funcionarios", json={"nome": "Pessoa", "cpf": f.cpf, "salario": "10"}, headers=b.h(pb)).json()["id"]
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": fid, "valor": "10"}]}, headers=a.h(pa))
    assert r.status_code in (400, 404) or (r.status_code == 200 and all(i["situacao"] == "erro" for i in r.json()["resultados"])), r.text
    assert a.saldo(pa) == "100.00" and f.saldo() == "0.00"


def test_adv_cobranca_cancelada_paga_e_estorno_repetido(cliente):
    dono, pagador = Pessoa(cliente, "cobrador@ex.com"), Pessoa(cliente, "pagador@ex.com")
    pj = dono.abrir_empresa()["numero"]
    depositar(cliente, pagador.numero, 100)
    def criar():
        r = cliente.post("/cobrancas", json={"valor": "10", "pagador_documento": pagador.cpf}, headers=dono.h(pj))
        assert r.status_code == 201
        return r.json()[0]["txid"]
    cancelada = criar()
    assert cliente.post(f"/cobrancas/{cancelada}/cancelar", headers=dono.h(pj)).status_code == 204
    assert cliente.post(f"/cobrancas/{cancelada}/pagar", json={}, headers=pagador.h()).status_code in (400, 409)
    paga = criar()
    assert cliente.post(f"/cobrancas/{paga}/pagar", json={}, headers=pagador.h()).status_code == 200
    assert cliente.post(f"/cobrancas/{paga}/pagar", json={}, headers=pagador.h()).status_code in (400, 409)
    assert cliente.post(f"/cobrancas/{paga}/estornar", json={}, headers=dono.h(pj)).status_code == 200
    assert cliente.post(f"/cobrancas/{paga}/estornar", json={}, headers=dono.h(pj)).status_code in (400, 409)
    assert pagador.saldo() == "100.00" and dono.saldo(pj) == "0.00"


def test_adv_idor_recorrencia_e_rotas_complementares(cliente):
    dono, pagador, atacante = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "pagador@ex.com"), Pessoa(cliente, "atacante@ex.com")
    pj, pa = dono.abrir_empresa()["numero"], atacante.abrir_empresa()["numero"]
    autorizacao = cliente.post("/pix-automatico/autorizacoes", headers=dono.h(pj), json={
        "pagador": conta_ref(pagador.numero), "valor_maximo": "50", "periodicidade": "mensal", "descricao": "Teste"})
    assert autorizacao.status_code == 201, autorizacao.text
    aid = autorizacao.json()["id"]
    for acao in ("aceitar", "recusar", "cancelar", "cobrancas"):
        r = cliente.post(f"/pix-automatico/autorizacoes/{aid}/{acao}", headers=atacante.h(pa),
            json={"valor": "10", "vencimento": "2026-10-10"})
        assert r.status_code in (403, 404), (acao, r.text)
    vinc = _convidar(cliente, dono, pj, pagador, "consulta").json()["id"]
    for acao in ("reativar",):
        assert cliente.post(f"/empresas/atual/vinculos/{vinc}/{acao}", headers=atacante.h(pa), json={"biometria": atacante.prova()}).status_code in (403, 404)
    disp = cliente.get("/seguranca/dispositivos", headers=dono.h()).json()[0]["id"]
    assert cliente.post(f"/seguranca/dispositivos/{disp}/desbloquear", headers=atacante.h(), json=atacante.prova()).status_code in (403, 404)
    for caminho in ("/admin/kyc/casos/1/decidir", "/admin/transacoes/1/liberar", "/admin/contestacoes/1/decidir"):
        assert cliente.post(caminho, json={"aprovar": True, "decisao": "aprovado"}, headers=atacante.h()).status_code == 403


def test_adv_respostas_privadas_sem_segredos(cliente):
    p = Pessoa(cliente, "vazamento@ex.com")
    pj = p.abrir_empresa()["numero"]
    for caminho, conta in (("/auth/eu", None), ("/auth/sessoes", None), ("/seguranca/dispositivos", None),
                            ("/empresas/atual/vinculos", pj), ("/empresas/atual/webhooks", pj)):
        r = cliente.get(caminho, headers=p.h(conta))
        assert r.status_code == 200
        for segredo in ("senha_hash", "embedding", "jwt_secret", "refresh_token", "privateKey", "Traceback"):
            assert segredo not in r.text
        assert "set-cookie" not in r.headers and "x-powered-by" not in r.headers


def test_adv_mass_assignment_cadastro_empresa_e_acesso(cliente):
    from tests.helpers import gerar_cpf, prova_cadastro
    r = cliente.post("/usuarios", json={"nome": "Pessoa Teste", "email": "extras@ex.com", "cpf": gerar_cpf(),
        "senha": SENHA, "biometria": prova_cadastro(cliente), "papel": "admin", "saldo": "99999", "kyc_status": "aprovado",
        "id": 999999, "tipo": "PJ", "senha_hash": "forjado"}, headers={"X-Dispositivo-Id": "extras"})
    assert r.status_code == 201
    assert r.json()["saldo"] == "0.00" and r.json()["titular_tipo"] == "PF"
    tk = login_completo(cliente, "extras@ex.com", SENHA, "extras")
    assert cliente.get("/admin/contas", headers={"Authorization": f"Bearer {tk['access_token']}", "X-Dispositivo-Id": "extras"}).status_code == 403
    dono, convidado = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "convidado@ex.com")
    pj = dono.abrir_empresa(saldo="999999", representante_usuario_id=999999, verificada_por="forjado", id=999999)["numero"]
    assert dono.saldo(pj) == "0.00"
    v = cliente.post("/empresas/atual/vinculos", headers=dono.h(pj), json={"nome": "Pessoa Teste", "cpf": convidado.cpf,
        "papel": "consulta", "status": "ativo", "ativo": True, "usuario_id": 999999, "empresa_id": 999999}).json()
    assert v["status"] == "pendente" and not v["ativo"]
    _aceitar(cliente, convidado, v["id"])
    r = cliente.patch(f"/empresas/atual/vinculos/{v['id']}", headers=dono.h(pj), json={"status": "revogado", "ativo": False,
        "usuario_id": 999999, "empresa_id": 999999, "papel": "consulta"})
    assert r.status_code == 200 and r.json()["status"] == "ativo"
    assert cliente.get("/contas/atual", headers=convidado.h(pj)).status_code == 200


def test_adv_mass_assignment_cobranca_recorrencia_folha_pix_e_webhook(cliente):
    dono, f, terceiro = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "func@ex.com"), Pessoa(cliente, "terceiro@ex.com")
    pj = dono.abrir_empresa()["numero"]
    depositar(cliente, pj, 100)
    extras = {"empresa_id": 999999, "carteira_id": 999999, "id": 999999, "status": "paga", "saldo": "999999"}
    cob = cliente.post("/cobrancas", headers=dono.h(pj), json={**extras, "valor": "10", "cbs": "999", "ibs": "999", "liquido": "999", "transacao_id": 999999}).json()[0]
    assert cob["status"] == "aberta" and cob["cbs"] == cob["ibs"] == "0.00" and cob["transacao_id"] is None
    auto = cliente.post("/pix-automatico/autorizacoes", headers=dono.h(pj), json={**extras, "pagador": conta_ref(f.numero),
        "descricao": "Teste", "valor_maximo": "10", "periodicidade": "mensal", "aceita_em": "2026-01-01"}).json()
    assert auto["status"] == "pendente" and auto["aceita_em"] is None
    func = cliente.post("/empresas/atual/funcionarios", headers=dono.h(pj), json={**extras, "nome": "Pessoa Teste", "cpf": f.cpf,
        "salario": "10", "ativo": False, "usuario_id": 999999}).json()
    assert func["ativo"] and func["id"] != 999999
    folha = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(pj), json={**extras, "itens": [{"funcionario_id": func["id"],
        "valor": "10", "destino": conta_ref(terceiro.numero), "destino_carteira_id": terceiro.conta["carteira_id"]}]} )
    assert folha.status_code == 200, folha.text
    assert f.saldo() == "10.00" and terceiro.saldo() == "0.00"
    chave = cliente.post("/pix/chaves", headers=dono.h(pj), json={**extras, "tipo": "aleatoria"}).json()
    assert chave["id"] != 999999
    assert f.transferir({"chave": chave["valor"]}, "1").status_code == 200
    assert dono.saldo(pj) == "91.00" and f.saldo() == "9.00"
    web = cliente.post("/empresas/atual/webhooks", headers=dono.h(pj), json={**extras, "url": "https://exemplo.com/evento",
        "eventos": ["cobranca.paga"], "segredo": "segredo-forjado"}).json()
    assert web["id"] != 999999 and web["segredo"] != "segredo-forjado"
    lista = cliente.get("/empresas/atual/webhooks", headers=dono.h(pj)).json()
    assert all("segredo" not in item for item in lista)


def test_adv_convite_cpf_cadastrado_e_inexistente_mesmo_contrato(cliente):
    from tests.helpers import gerar_cpf
    dono, p = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "existente@ex.com")
    pj = dono.abrir_empresa()["numero"]
    respostas = [cliente.post("/empresas/atual/vinculos", headers=dono.h(pj), json={"nome": "Pessoa Teste", "cpf": cpf,
        "papel": "consulta"}) for cpf in (p.cpf, gerar_cpf())]
    assert all(r.status_code == 201 for r in respostas)
    assert respostas[0].json().keys() == respostas[1].json().keys()
    assert all(r.json()["status"] == "pendente" and r.json()["usuario_id"] is None for r in respostas)
