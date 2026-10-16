"""Regressão dos achados de REVISAO-PROBLEMAS.md (14/10/2026), R01-R06 e R10.

Cada teste reproduz o cenário do relatório e afirma o comportamento corrigido.
Os de concorrência (R09) ficam em test_concorrencia_extra_postgres.py: no SQLite
em memória tudo é serializado e eles não provariam nada.
"""

import sys
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from tests.helpers import SENHA, Pessoa, conta_ref, depositar, gerar_chave_nfe, gerar_cnpj
from tests.test_pj_regras_bancarias import _decidir, _empresa

AMANHA = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)


def _pendente(cliente, quem, n, oid):
    return next(p for p in cliente.get("/empresas/atual/pendentes?status=", headers=quem.h(n)).json()
                if p["id"] == oid)


# ------------------------------------------------------------------ R01: reenvio não paga duas vezes


def test_r01_reenvio_de_pix_ja_pago_devolve_o_mesmo_pagamento(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 100, {})], saldo=1000)
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    r1 = op.transferir(conta_ref(forn.numero), "60.00", conta=n, idempotency_key="review-reenvio")
    assert r1.status_code == 200, r1.text
    # Antes: a alçada do dia (60 + 60 > 100) mandava o reenvio para uma pendência nova.
    r2 = op.transferir(conta_ref(forn.numero), "60.00", conta=n, idempotency_key="review-reenvio")
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == r1.json()["id"]
    assert cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).json() == []
    assert forn.saldo() == "60.00"
    # A mesma chave com outro valor continua sendo conflito, não um pagamento novo.
    r3 = op.transferir(conta_ref(forn.numero), "61.00", conta=n, idempotency_key="review-reenvio")
    assert r3.status_code == 409, r3.text
    assert forn.saldo() == "60.00"


def test_r01_reenvio_de_pendencia_no_dia_seguinte_nao_vira_pagamento_direto(cliente, relogio):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 100, {})], saldo=1000)
    op, forn = eq["op"][0], Pessoa(cliente, "forn@ex.com")
    assert op.transferir(conta_ref(forn.numero), "60.00", conta=n).status_code == 200
    r = op.transferir(conta_ref(forn.numero), "60.00", conta=n, idempotency_key="reenvio-amanha")
    assert r.status_code == 202, r.text
    oid = r.json()["operacao_id"]
    # No dia seguinte a alçada diária zerou; o reenvio ainda é a mesma intenção.
    relogio.definir(AMANHA)
    r = op.transferir(conta_ref(forn.numero), "60.00", conta=n, idempotency_key="reenvio-amanha")
    assert r.status_code == 202 and r.json()["operacao_id"] == oid, r.text
    assert _decidir(cliente, dono, n, oid).json()["status"] == "aprovada"
    r = op.transferir(conta_ref(forn.numero), "60.00", conta=n, idempotency_key="reenvio-amanha")
    assert r.status_code == 202 and r.json()["operacao_id"] == oid, r.text
    assert forn.saldo() == "120.00"


def test_r01_reenvio_de_folha_paga_na_hora_nao_gera_pendencia(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 100, {})], saldo=1000)
    op, func = eq["op"][0], Pessoa(cliente, "func@ex.com")
    fid = _cadastrar_funcionario(cliente, dono, n, func, "60.00")
    corpo = {"itens": [{"funcionario_id": fid}], "descricao": "Salário 10/2026"}
    r1 = cliente.post("/empresas/atual/folha/pagar", json=corpo, headers=op.h(n))
    assert r1.status_code == 200 and r1.json()["resultados"][0]["situacao"] == "pago", r1.text
    r2 = cliente.post("/empresas/atual/folha/pagar", json=corpo, headers=op.h(n))
    assert r2.status_code == 200, r2.text
    assert r2.json()["resultados"] == r1.json()["resultados"]
    assert cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).json() == []
    assert func.saldo() == "60.00"


# ------------------------------------------------------------------ R02: devolução respeita a alçada


def _pix_para_empresa(cliente, n, valor):
    pagador = Pessoa(cliente, f"pagador{valor.replace('.', '_')}@ex.com")
    depositar(cliente, pagador.numero, valor)
    r = pagador.transferir(conta_ref(n), valor)
    assert r.status_code == 200 and r.json()["status"] == "concluida", r.text
    return pagador, r.json()["id"]


def test_r02_devolucao_acima_da_alcada_vira_pendencia(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 10, {})], saldo=1)
    op = eq["op"][0]
    pagador, tid = _pix_para_empresa(cliente, n, "100.00")
    corpo = {"valor": "100.00", "idempotency_key": "devolve-100"}
    r = cliente.post(f"/pagamentos/transacoes/{tid}/devolver", json=corpo, headers=op.h(n))
    assert r.status_code == 202, r.text
    oid = r.json()["operacao_id"]
    assert (dono.saldo(n), pagador.saldo()) == ("101.00", "0.00")
    p = _pendente(cliente, dono, n, oid)
    assert (p["tipo"], p["status"]) == ("devolucao", "pendente")
    # Reenvio da mesma devolução (mesma chave) devolve a mesma pendência.
    r = cliente.post(f"/pagamentos/transacoes/{tid}/devolver", json=corpo, headers=op.h(n))
    assert r.status_code == 202 and r.json()["operacao_id"] == oid
    r = _decidir(cliente, dono, n, oid)
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text
    assert (dono.saldo(n), pagador.saldo()) == ("1.00", "100.00")


def test_r02_devolucoes_somam_na_alcada_diaria(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 10, {})], saldo=1)
    op = eq["op"][0]
    _, t1 = _pix_para_empresa(cliente, n, "6.00")
    _, t2 = _pix_para_empresa(cliente, n, "7.00")
    assert cliente.post(f"/pagamentos/transacoes/{t1}/devolver", json={}, headers=op.h(n)).status_code == 201
    r = cliente.post(f"/pagamentos/transacoes/{t2}/devolver", json={}, headers=op.h(n))
    assert r.status_code == 202, r.text  # 6 + 7 > 10 no dia
    assert dono.saldo(n) == "8.00"


def test_r02_devolucao_dentro_da_alcada_e_da_pf_continua_direta(cliente):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 50, {})], saldo=1)
    _, tid = _pix_para_empresa(cliente, n, "20.00")
    r = cliente.post(f"/pagamentos/transacoes/{tid}/devolver", json={"valor": "20.00"}, headers=eq["op"][0].h(n))
    assert r.status_code == 201 and r.json()["tipo"] == "devolucao", r.text


# ------------------------------------------------------------------ R03: lote não aborta no meio


def test_r03_conflito_de_chave_vira_erro_do_item_e_o_lote_continua(cliente):
    a, b = Pessoa(cliente, "lote.a@ex.com"), Pessoa(cliente, "lote.b@ex.com")
    depositar(cliente, a.numero, 100)
    assert a.transferir(conta_ref(b.numero), "1.00", idempotency_key="review-conflito").status_code == 200
    itens = [{"destino": conta_ref(b.numero), "valor": "2.00", "idempotency_key": "lote-novo-1"},
             {"destino": conta_ref(b.numero), "valor": "3.00", "idempotency_key": "review-conflito"},
             {"destino": conta_ref(b.numero), "valor": "4.00", "idempotency_key": "lote-novo-2"}]
    r = cliente.post("/pagamentos/lote", json={"itens": itens, "senha": SENHA}, headers=a.h())
    assert r.status_code == 200, r.text
    assert [i["situacao"] for i in r.json()] == ["concluida", "erro", "concluida"]
    assert "idempotência" in r.json()[1]["erro"]
    assert b.saldo() == "7.00"


# ------------------------------------------------------------------ R04/R05: folha aprovada x paga


def _cadastrar_funcionario(cliente, dono, n, func, salario):
    r = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                     json={"nome": "Funcionario Silva", "cpf": func.cpf, "salario": salario})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _folha_pendente(cliente, saldo, salarios):
    dono, n, eq = _empresa(cliente, "PME", [("op", "operador", 10, {})], saldo=saldo)
    op = eq["op"][0]
    funcs = [Pessoa(cliente, f"func{i}@ex.com") for i in range(len(salarios))]
    fids = [_cadastrar_funcionario(cliente, dono, n, f, s) for f, s in zip(funcs, salarios)]
    r = cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": f} for f in fids]},
                     headers=op.h(n))
    assert r.status_code == 200 and "pendente" in r.json(), r.text
    return dono, n, op, funcs, fids, r.json()["pendente"]["id"]


def test_r04_folha_aprovada_sem_saldo_fica_como_falhou_com_os_itens(cliente):
    dono, n, _, (func,), (fid,), oid = _folha_pendente(cliente, 50, ["100.00"])
    r = _decidir(cliente, dono, n, oid)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "falhou"
    assert corpo["resultado"]["executados"] == 0 and corpo["resultado"]["itens"] == 1
    assert corpo["resultado"]["resultados"][0]["situacao"] == "erro"
    assert func.saldo() == "0.00"
    # Repetir depois de completar o saldo paga só o que faltou.
    depositar(cliente, n, 100)
    r = cliente.post(f"/pagamentos/pendentes/{oid}/repetir", json={}, headers=dono.h(n))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "aprovada" and r.json()["resultado"]["executados"] == 1
    assert func.saldo() == "100.00"


def test_r04_folha_parcial_mostra_quem_recebeu_e_repetir_nao_paga_de_novo(cliente):
    dono, n, op, (f1, f2), _, oid = _folha_pendente(cliente, 100, ["60.00", "60.00"])
    corpo = _decidir(cliente, dono, n, oid).json()
    assert corpo["status"] == "aprovada"
    res = corpo["resultado"]
    assert (res["parcial"], res["executados"], res["itens"]) == (True, 1, 2)
    assert sorted(i["situacao"] for i in res["resultados"]) == ["erro", "pago"]
    # quem lançou não repete (não tem poder de aprovar este valor)
    assert cliente.post(f"/pagamentos/pendentes/{oid}/repetir", json={}, headers=op.h(n)).status_code == 403
    depositar(cliente, n, 100)
    r = cliente.post(f"/pagamentos/pendentes/{oid}/repetir", json={}, headers=dono.h(n))
    assert r.status_code == 200 and r.json()["resultado"]["parcial"] is False, r.text
    assert (f1.saldo(), f2.saldo(), dono.saldo(n)) == ("60.00", "60.00", "80.00")
    # Nada mais a repetir.
    assert cliente.post(f"/pagamentos/pendentes/{oid}/repetir", json={}, headers=dono.h(n)).status_code == 409
    assert (f1.saldo(), f2.saldo()) == ("60.00", "60.00")


def test_r05_funcionario_desligado_nao_recebe_folha_que_aguardava_aprovacao(cliente):
    dono, n, _, (func,), (fid,), oid = _folha_pendente(cliente, 500, ["100.00"])
    assert cliente.delete(f"/empresas/atual/funcionarios/{fid}", headers=dono.h(n)).status_code == 204
    r = _decidir(cliente, dono, n, oid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "falhou"
    item = r.json()["resultado"]["resultados"][0]
    assert item["situacao"] == "erro" and "desligado" in item["erro"]
    assert func.saldo() == "0.00"
    # O desligamento também vale para a repetição.
    assert cliente.post(f"/pagamentos/pendentes/{oid}/repetir", json={}, headers=dono.h(n)).status_code == 200
    assert func.saldo() == "0.00"


def test_r05_pendencia_da_folha_mostra_desligamento_na_listagem(cliente):
    dono, n, _, _, (fid,), oid = _folha_pendente(cliente, 500, ["100.00"])
    assert cliente.delete(f"/empresas/atual/funcionarios/{fid}", headers=dono.h(n)).status_code == 204
    p = _pendente(cliente, dono, n, oid)
    assert p["funcionarios_desligados"] == [fid]


# ------------------------------------------------------------------ R06: parcela menor que um centavo


def test_r06_parcelamento_abaixo_de_um_centavo_por_parcela_e_400(cliente):
    dono = Pessoa(cliente, "dono.cob@ex.com")
    n = dono.abrir_empresa()["numero"]
    r = cliente.post("/cobrancas", json={"valor": "0.01", "parcelas": 12, "vencimento": "2026-10-15"},
                     headers=dono.h(n))
    assert r.status_code == 400, r.text
    assert "parcela" in r.json()["detail"].lower()
    r = cliente.post("/cobrancas", json={"valor": "0.12", "parcelas": 12, "vencimento": "2026-10-15"},
                     headers=dono.h(n))
    assert r.status_code == 201 and len(r.json()) == 12, r.text


def test_r06_imposto_que_nao_cabe_na_parcela_e_400(cliente):
    dono = Pessoa(cliente, "dono.cob2@ex.com")
    cnpj = gerar_cnpj()
    n = dono.abrir_empresa(cnpj=cnpj)["numero"]
    nota = {"chave": gerar_chave_nfe(cnpj), "cbs": "0.05", "ibs": "0.00"}
    r = cliente.post("/cobrancas", json={"valor": "0.12", "parcelas": 12, "vencimento": "2026-10-15",
                                         "nota_fiscal": nota}, headers=dono.h(n))
    assert r.status_code == 400, r.text


# ------------------------------------------------------------------ R10: worker de PDF


def test_r10_ambiente_do_worker_tem_o_minimo_do_sistema_sem_segredos(monkeypatch):
    from app.core import arquivos

    monkeypatch.setenv("JWT_SECRET", "nao-pode-vazar")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    env = arquivos._ambiente_pdf()
    assert "JWT_SECRET" not in env and env["PYTHONNOUSERSITE"] == "1"
    if sys.platform == "win32":
        assert env.get("SYSTEMROOT") == r"C:\Windows"


def test_r10_worker_que_nao_inicia_e_503_e_nao_413(monkeypatch):
    from app.core import arquivos

    monkeypatch.setattr(arquivos, "_COMANDO_PDF", (sys.executable, "-c", "import sys; sys.exit(1)"))
    with pytest.raises(HTTPException) as erro:
        arquivos._validar_pdf(b"pdf-teste")
    assert erro.value.status_code == 503


def test_r10_worker_que_estoura_depois_de_iniciar_continua_413(monkeypatch):
    from app.core import arquivos

    codigo = "import sys; sys.stdout.buffer.write(b'pronto\\n'); sys.stdout.flush(); sys.exit(1)"
    monkeypatch.setattr(arquivos, "_COMANDO_PDF", (sys.executable, "-c", codigo))
    with pytest.raises(HTTPException) as erro:
        arquivos._validar_pdf(b"pdf-teste")
    assert erro.value.status_code == 413
