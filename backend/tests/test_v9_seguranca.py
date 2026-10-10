"""v9: login em 2 fatores, sessões presas ao aparelho, equipe PJ por porte,
folha, KYC de documentos, política de senha e cabeçalhos HTTP."""

import base64

import pytest

from tests.helpers import QUADROS, SENHA, Pessoa, conta_ref, depositar, gerar_cpf, login, prova_cadastro


def _png(lado: int = 120) -> str:
    """PNG de ruído (> 1 KB, magic bytes de PNG): passa na validação de arquivo."""
    import cv2
    import numpy as np

    img = np.random.default_rng(1).integers(0, 255, (lado, lado, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def _etapa_senha(cliente, email, dispositivo):
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA}, headers={"X-Dispositivo-Id": dispositivo})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ login 2 fatores


def test_senha_sozinha_nao_entra(cliente):
    p = Pessoa(cliente, "p@ex.com")
    r = _etapa_senha(cliente, "p@ex.com", p.dispositivo)
    assert r["mfa_requerido"] is True and r["access_token"] is None
    assert r["desafio"]["modo"] == "login" and r["desafio"]["passos"]
    # o mfa_token não é um token de acesso
    assert cliente.get("/contas/atual", headers={"Authorization": f"Bearer {r['mfa_token']}",
                                                 "X-Dispositivo-Id": p.dispositivo}).status_code == 401


def test_mfa_sem_rosto_ou_de_outro_aparelho_nao_entra(cliente):
    p = Pessoa(cliente, "p@ex.com")
    r = _etapa_senha(cliente, "p@ex.com", p.dispositivo)
    bio = {"desafio_id": r["desafio"]["desafio_id"], "quadros": QUADROS}
    # sem biometria: corpo inválido
    assert cliente.post("/auth/login/mfa", json={"mfa_token": r["mfa_token"]},
                        headers={"X-Dispositivo-Id": p.dispositivo}).status_code == 422
    # etapa 2 em outro aparelho
    r2 = cliente.post("/auth/login/mfa", json={"mfa_token": r["mfa_token"], "biometria": bio},
                      headers={"X-Dispositivo-Id": "aparelho-do-golpista"})
    assert r2.status_code == 401


def test_mfa_token_nao_e_reutilizavel(cliente):
    p = Pessoa(cliente, "p@ex.com")
    h = {"X-Dispositivo-Id": p.dispositivo}
    r = _etapa_senha(cliente, "p@ex.com", p.dispositivo)
    ok = cliente.post("/auth/login/mfa", headers=h, json={
        "mfa_token": r["mfa_token"], "biometria": {"desafio_id": r["desafio"]["desafio_id"], "quadros": QUADROS}})
    assert ok.status_code == 200 and ok.json()["access_token"]
    # mesmo mfa_token com um desafio novo: recusado
    novo = cliente.post("/auth/login/mfa/desafio", json={"mfa_token": r["mfa_token"]}, headers=h)
    if novo.status_code == 201:
        de_novo = cliente.post("/auth/login/mfa", headers=h, json={
            "mfa_token": r["mfa_token"], "biometria": {"desafio_id": novo.json()["desafio_id"], "quadros": QUADROS}})
        assert de_novo.status_code == 401
    else:
        assert novo.status_code == 401


def test_desafio_de_outra_pessoa_nao_completa_o_login(cliente):
    Pessoa(cliente, "a@ex.com")
    b = Pessoa(cliente, "b@ex.com")
    r = _etapa_senha(cliente, "a@ex.com", "aparelho-a2")
    r2 = cliente.post("/auth/login/mfa", headers={"X-Dispositivo-Id": "aparelho-a2"}, json={
        "mfa_token": r["mfa_token"], "biometria": b.prova()})
    assert r2.status_code == 401


def test_login_com_rosto_confia_no_aparelho(cliente):
    p = Pessoa(cliente, "p@ex.com")
    p.dispositivo = "notebook"
    p.token = login(cliente, "p@ex.com", SENHA, "notebook")
    assert cliente.get("/seguranca/dispositivos/atual", headers=p.h()).json()["confiavel"] is True


# ------------------------------------------------------------------ sessões e aparelhos


def test_encerrar_sessao_derruba_o_access(cliente):
    p = Pessoa(cliente, "p@ex.com")
    outro = login(cliente, "p@ex.com", SENHA, "tablet")
    h_tablet = {"Authorization": f"Bearer {outro}", "X-Dispositivo-Id": "tablet"}
    sessoes = cliente.get("/auth/sessoes", headers=p.h()).json()
    assert len(sessoes) == 2 and sum(s["atual"] for s in sessoes) == 1
    alvo = next(s for s in sessoes if not s["atual"])
    assert cliente.delete(f"/auth/sessoes/{alvo['sessao_id']}", headers=p.h()).status_code == 204
    assert cliente.get("/contas/atual", headers=h_tablet).status_code == 401
    assert cliente.get("/contas/atual", headers=p.h()).status_code == 200


def test_encerrar_outras_sessoes(cliente):
    p = Pessoa(cliente, "p@ex.com")
    t = login(cliente, "p@ex.com", SENHA, "tablet")
    assert cliente.post("/auth/sessoes/encerrar-outras", headers=p.h()).json()["encerradas"] == 1
    assert cliente.get("/contas/atual", headers={"Authorization": f"Bearer {t}", "X-Dispositivo-Id": "tablet"}).status_code == 401
    assert cliente.get("/contas/atual", headers=p.h()).status_code == 200


def test_bloquear_aparelho_roubado(cliente):
    p = Pessoa(cliente, "p@ex.com")
    roubado = login(cliente, "p@ex.com", SENHA, "celular-roubado")
    h_roubado = {"Authorization": f"Bearer {roubado}", "X-Dispositivo-Id": "celular-roubado"}
    aparelhos = cliente.get("/seguranca/dispositivos", headers=p.h()).json()
    alvo = next(a for a in aparelhos if a["id"] != cliente.get("/seguranca/dispositivos/atual", headers=p.h()).json()["id"])
    assert cliente.post(f"/seguranca/dispositivos/{alvo['id']}/bloquear", headers=p.h()).status_code == 200
    # a sessão do aparelho cai na hora e um novo login nele é recusado
    assert cliente.get("/contas/atual", headers=h_roubado).status_code == 401
    r = cliente.post("/auth/login", json={"email": "p@ex.com", "senha": SENHA},
                     headers={"X-Dispositivo-Id": "celular-roubado"})
    if r.status_code == 200:
        r = cliente.post("/auth/login/mfa", headers={"X-Dispositivo-Id": "celular-roubado"}, json={
            "mfa_token": r.json()["mfa_token"],
            "biometria": {"desafio_id": r.json()["desafio"]["desafio_id"], "quadros": QUADROS}})
    assert r.status_code in (401, 403)
    # desbloquear exige o rosto
    assert cliente.post(f"/seguranca/dispositivos/{alvo['id']}/desbloquear", json=p.prova(), headers=p.h()).status_code == 200


# ------------------------------------------------------------------ equipe PJ


def _convidar(cliente, admin, n, pessoa, papel, alcada=None, **extra):
    corpo = {"cpf": pessoa.cpf, "nome": "Pessoa Convidada", "papel": papel, "biometria": admin.prova(), **extra}
    if alcada is not None:
        corpo["alcada"] = str(alcada)
    return cliente.post("/empresas/atual/vinculos", json=corpo, headers=admin.h(n))


def _aceitar(cliente, pessoa, vinculo_id):
    return cliente.post(f"/convites/{vinculo_id}/aceitar", json={"biometria": pessoa.prova()}, headers=pessoa.h())


def test_convite_por_cpf_aceite_suspender_e_revogar(cliente):
    dono, op = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "op@ex.com")
    n = dono.abrir_empresa()["numero"]
    r = _convidar(cliente, dono, n, op, "operador", alcada=500)
    assert r.status_code == 201 and r.json()["status"] == "pendente"
    v = r.json()
    assert "*" in v["cpf"]  # CPF sempre mascarado
    # enquanto pendente, não opera a empresa
    assert cliente.get("/contas/atual", headers=op.h(n)).status_code in (403, 404)
    # convite aparece para a pessoa certa, e só para ela
    assert [c["id"] for c in cliente.get("/convites", headers=op.h()).json()] == [v["id"]]
    assert cliente.get("/convites", headers=dono.h()).json() == []
    assert _aceitar(cliente, op, v["id"]).json()["status"] == "ativo"
    assert cliente.get("/contas/atual", headers=op.h(n)).status_code == 200
    # suspender corta o acesso; reativar devolve
    assert cliente.post(f"/empresas/atual/vinculos/{v['id']}/suspender", headers=dono.h(n)).json()["status"] == "suspenso"
    assert cliente.get("/contas/atual", headers=op.h(n)).status_code in (403, 404)
    r = cliente.post(f"/empresas/atual/vinculos/{v['id']}/reativar", json={"biometria": dono.prova()}, headers=dono.h(n))
    assert r.status_code == 200 and r.json()["status"] == "ativo"
    # revogar é definitivo
    assert cliente.delete(f"/empresas/atual/vinculos/{v['id']}", headers=dono.h(n)).status_code == 200
    assert cliente.get("/contas/atual", headers=op.h(n)).status_code in (403, 404)


def test_convite_de_outra_pessoa_nao_pode_ser_aceito(cliente):
    dono, op, intruso = (Pessoa(cliente, f"{x}@ex.com") for x in ("dono", "op", "intruso"))
    n = dono.abrir_empresa()["numero"]
    vid = _convidar(cliente, dono, n, op, "consulta").json()["id"]
    assert _aceitar(cliente, intruso, vid).status_code == 404


def test_ultimo_admin_nao_sai(cliente):
    dono = Pessoa(cliente, "dono@ex.com")
    n = dono.abrir_empresa()["numero"]
    eu = next(v for v in cliente.get("/empresas/atual/vinculos", headers=dono.h(n)).json() if v["papel"] == "admin")
    assert cliente.post(f"/empresas/atual/vinculos/{eu['id']}/suspender", headers=dono.h(n)).status_code == 400
    assert cliente.delete(f"/empresas/atual/vinculos/{eu['id']}", headers=dono.h(n)).status_code == 400


def test_mei_so_convida_operador_com_alcada_ou_consulta(cliente):
    dono, contador = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "contador@ex.com")
    n = dono.abrir_empresa(porte="MEI", regime_apuracao="mei")["numero"]
    assert _convidar(cliente, dono, n, contador, "admin").status_code == 403
    assert _convidar(cliente, dono, n, contador, "aprovador", alcada=100).status_code == 403
    assert _convidar(cliente, dono, n, contador, "operador").status_code == 400  # sem alçada
    assert _convidar(cliente, dono, n, contador, "consulta").status_code == 201


def test_grande_quatro_olhos_na_gestao_de_acesso(cliente):
    dono, socio, nova = (Pessoa(cliente, f"{x}@ex.com") for x in ("dono", "socio", "nova"))
    n = dono.abrir_empresa(porte="GRANDE")["numero"]
    # com 1 admin só, não há a quem pedir: o convite segue direto
    v = _convidar(cliente, dono, n, socio, "admin")
    assert v.status_code == 201 and v.json()["status"] == "pendente"
    assert _aceitar(cliente, socio, v.json()["id"]).status_code == 200
    # agora com 2 admins: dar poder fica aguardando outro admin
    r = _convidar(cliente, dono, n, nova, "aprovador", alcada=10000)
    assert r.status_code == 201 and r.json()["status"] == "aguardando"
    vid = r.json()["id"]
    assert _aceitar(cliente, nova, vid).status_code == 404  # ainda não pode aceitar
    [op] = [p for p in cliente.get("/empresas/atual/pendentes", headers=socio.h(n)).json() if p["tipo"] == "acesso"]
    # quem pediu não aprova a si mesmo
    assert cliente.post(f"/pagamentos/pendentes/{op['id']}/decidir", json={"aprovar": True, "biometria": dono.prova()},
                        headers=dono.h(n)).status_code == 403
    r = cliente.post(f"/pagamentos/pendentes/{op['id']}/decidir", json={"aprovar": True, "biometria": socio.prova()},
                     headers=socio.h(n))
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text
    # aprovado pelo outro admin, o convite libera e a pessoa aceita
    assert _aceitar(cliente, nova, vid).json()["status"] == "ativo"


def test_grande_operador_sempre_com_alcada(cliente):
    dono, op = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "op@ex.com")
    n = dono.abrir_empresa(porte="GRANDE")["numero"]
    assert _convidar(cliente, dono, n, op, "operador").status_code == 400


def test_grande_duas_aprovacoes_acima_do_limite(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "limite_duas_aprovacoes_reais", 5000.0)
    dono, op, apr, forn = (Pessoa(cliente, f"{x}@ex.com") for x in ("dono", "op", "apr", "forn"))
    n = dono.abrir_empresa(porte="GRANDE")["numero"]
    depositar(cliente, n, 50000)
    for pessoa, papel, alcada in ((op, "operador", 100), (apr, "aprovador", 20000)):
        v = _convidar(cliente, dono, n, pessoa, papel, alcada=alcada)
        assert v.status_code == 201, v.text
        assert _aceitar(cliente, pessoa, v.json()["id"]).status_code == 200
    r = op.transferir(conta_ref(forn.numero), 6000, conta=n)
    assert r.status_code == 202, r.text
    oid = r.json()["operacao_id"]
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": apr.prova()}, headers=apr.h(n))
    assert r.status_code == 200 and r.json()["status"] == "pendente", r.text
    assert dono.saldo(n) == "50000.00"
    # a mesma pessoa não conta duas vezes
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": apr.prova()}, headers=apr.h(n))
    assert r.status_code == 409
    r = cliente.post(f"/pagamentos/pendentes/{oid}/decidir", json={"aprovar": True, "biometria": dono.prova()}, headers=dono.h(n))
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text
    assert dono.saldo(n) == "44000.00"


# ------------------------------------------------------------------ folha


def test_folha_so_paga_funcionario_com_conta_pf(cliente):
    dono, func = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "func@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, n, 10000)
    r = cliente.post("/empresas/atual/funcionarios", json={"nome": "Func Silva", "cpf": func.cpf, "salario": "300.00"},
                     headers=dono.h(n))
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    sem_conta = cliente.post("/empresas/atual/funcionarios", json={"nome": "Sem Conta", "cpf": gerar_cpf()},
                             headers=dono.h(n)).json()["id"]
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": fid}]}, headers=dono.h(n))
    assert r.status_code == 200, r.text
    assert r.json()["resultados"][0]["situacao"] == "pago"
    assert func.saldo() == "300.00"
    # sem conta PF na Astro: recusado
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": sem_conta, "valor": "10"}]},
                     headers=dono.h(n))
    assert r.status_code == 409
    # funcionário de outra empresa / inexistente: 404
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": 99999, "valor": "10"}]},
                     headers=dono.h(n))
    assert r.status_code == 404


# ------------------------------------------------------------------ KYC


def _cadastro_com_documento(cliente, *, cpf=None, documento=None):
    return cliente.post("/usuarios", headers={"X-Dispositivo-Id": "cel-kyc"}, json={
        "nome": "Maria Souza Lima", "email": "maria@ex.com", "senha": SENHA, "cpf": cpf or gerar_cpf(),
        "data_nascimento": "1990-05-04", "celular": "11987654321", "biometria": prova_cadastro(cliente),
        "documento": documento or {"tipo": "rg", "frente": _png(), "verso": _png(130)}})


def test_documento_exige_frente_e_verso(cliente):
    for tipo in ("rg", "cnh", "cin"):
        r = _cadastro_com_documento(cliente, documento={"tipo": tipo, "frente": _png()})
        assert r.status_code == 400 and "verso" in r.json()["detail"], tipo
    # passaporte é uma página só
    assert _cadastro_com_documento(cliente, documento={"tipo": "passaporte", "frente": _png()}).status_code == 201


def test_kyc_obrigatorio_exige_documento(cliente, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "kyc_documento_obrigatorio", True)
    r = cliente.post("/usuarios", json={"nome": "Maria Souza", "email": "m@ex.com", "senha": SENHA, "cpf": gerar_cpf(),
                                        "biometria": prova_cadastro(cliente)})
    assert r.status_code == 400
    r = _cadastro_com_documento(cliente)
    assert r.status_code == 201, r.text
    assert r.json()["kyc"]["status"] == "aprovado"


def test_kyc_cpf_diferente_reprova_e_nao_cria_conta(cliente, monkeypatch):
    from app.services import ocr_service

    outro = gerar_cpf()
    monkeypatch.setattr(ocr_service, "provedor", lambda: "tesseract")
    monkeypatch.setattr(ocr_service, "extrair_texto", lambda img: f"NOME MARIA SOUZA LIMA CPF {outro} NASC 04/05/1990")
    r = _cadastro_com_documento(cliente)
    assert r.status_code == 422 and "CPF" in r.json()["detail"]
    assert cliente.post("/auth/login", json={"email": "maria@ex.com", "senha": SENHA}).status_code == 401


def test_kyc_documento_que_confere_aprova(cliente, monkeypatch):
    from app.services import ocr_service

    cpf = gerar_cpf()
    monkeypatch.setattr(ocr_service, "provedor", lambda: "tesseract")
    monkeypatch.setattr(ocr_service, "extrair_texto",
                        lambda img: f"NOME MARIA SOUZA LIMA CPF {cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]} NASC 04/05/1990")
    r = _cadastro_com_documento(cliente, cpf=cpf)
    assert r.status_code == 201 and r.json()["kyc"]["status"] == "aprovado", r.text


def test_arquivo_nao_imagem_e_recusado(cliente):
    from fastapi import HTTPException

    from app.core import arquivos

    exe = base64.b64encode(b"MZ" + b"\0" * 2048).decode()
    with pytest.raises(HTTPException) as e:
        arquivos.validar_arquivo(exe, permitidos=arquivos.IMAGENS, limite_bytes=10_000_000)
    assert e.value.status_code == 415


# ------------------------------------------------------------------ funções puras


def test_pdf_com_javascript_e_recusado():
    from fastapi import HTTPException

    from app.core import arquivos

    pdf = b"%PDF-1.4\n1 0 obj << /Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >> endobj\n"
    pdf += b"%" + b"x" * 2048 + b"\n%%EOF"
    with pytest.raises(HTTPException) as e:
        arquivos.validar_arquivo(base64.b64encode(pdf).decode(), permitidos=arquivos.DOCUMENTOS, limite_bytes=10_000_000)
    assert e.value.status_code == 415


def test_ocr_encontra_cpf_valido_e_datas():
    from datetime import date

    from app.services import ocr_service

    cpf = gerar_cpf()
    texto = f"CPF {cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]} e lixo 123.456.789-00 NASC 04/05/1990 VAL 01/02/2031"
    assert ocr_service.encontrar_cpfs(texto) == [cpf]  # o inválido é descartado
    assert date(1990, 5, 4) in ocr_service.encontrar_datas(texto)
    assert ocr_service.nome_confere("Maria Souza Lima", "NOME MARIA SOUZZA LIMA")  # tolera erro de OCR
    assert not ocr_service.nome_confere("Maria Souza Lima", "NOME JOAO PEREIRA")


def test_mrz_td3_com_digitos_icao():
    from datetime import date

    from app.services import ocr_service

    # Exemplo oficial do ICAO Doc 9303.
    texto = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
    m = ocr_service.ler_mrz(texto)
    assert m and m["formato"] == "TD3" and m["valido"] is True
    assert m["nascimento"] == date(1974, 8, 12) and m["numero"] == "L898902C3"
    adulterado = texto.replace("7408122", "7408132")
    assert ocr_service.ler_mrz(adulterado)["valido"] is False


@pytest.mark.parametrize("senha", ["curta", "Flamengo2024!", "1234567890", "aaaaaaaaaaaa", "qwertyuiop"])
def test_politica_de_senha_recusa(senha):
    from fastapi import HTTPException

    from app.services import senha_policy

    with pytest.raises(HTTPException):
        senha_policy.validar(senha, email="maria@ex.com", nome="Maria Souza")


def test_politica_de_senha_recusa_dados_pessoais():
    from fastapi import HTTPException

    from app.services import senha_policy

    cpf = gerar_cpf()
    for senha in (f"x{cpf}y", "souzamaria!!", "MARIAsouza#2026"):
        with pytest.raises(HTTPException):
            senha_policy.validar(senha, email="maria@ex.com", cpf=cpf, nome="Maria Souza")
    senha_policy.validar(SENHA, email="maria@ex.com", cpf=cpf, nome="Maria Souza")


def test_cadastro_com_senha_fraca_recusado(cliente):
    r = cliente.post("/usuarios", json={"nome": "Maria Souza", "email": "m@ex.com", "senha": "senha12345",
                                        "cpf": gerar_cpf(), "biometria": prova_cadastro(cliente)})
    assert r.status_code == 400 and "comum" in r.json()["detail"]


# ------------------------------------------------------------------ HTTP


def test_cabecalhos_de_seguranca_e_problem_json(cliente):
    r = cliente.get("/contas/atual")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    corpo = r.json()
    assert {"type", "title", "status", "detail", "request_id"} <= corpo.keys()
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers.get("x-request-id") == corpo["request_id"]


def test_erro_de_validacao_nao_ecoa_o_valor(cliente):
    segredo = "<script>alert(1)</script>"
    r = cliente.post("/auth/login", json={"email": segredo, "senha": ""})
    assert r.status_code == 422
    assert segredo not in r.text


def test_sessao_recusada_tem_www_authenticate_visivel_para_o_app(cliente):
    """O app só volta para o login em 401 com WWW-Authenticate (sessão); 401 de rosto não tem.
    Para o navegador deixar o app ler o header, o CORS precisa expô-lo."""
    r = cliente.get("/contas/atual", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 401
    assert r.headers.get("www-authenticate")
    expostos = r.headers.get("access-control-expose-headers", "").lower()
    assert "www-authenticate" in expostos
