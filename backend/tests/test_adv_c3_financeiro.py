"""Ataque C3: SQL monta registros legados ou mudança controlada de cadastro."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.helpers import Pessoa, conta_ref, depositar
from tests.test_folha_idempotencia import folha  # noqa: F401
from tests.test_pj_regras_bancarias import pendente, _decidir  # noqa: F401
from tests.test_conciliar_pendentes import (
    AGORA, _status, _rodar_job, _cai_antes_do_movimento, _cai_depois_do_movimento,
)
from tests.test_outbox_webhooks import loja  # noqa: F401
from tests.test_cobrancas import _cobrar


def _chaves():
    from app.db.base import SessionLocal
    from app.db.models import Transacao
    with SessionLocal() as s:
        return list(s.scalars(select(Transacao.idempotency_key).where(Transacao.idempotency_key.is_not(None))))


@pytest.mark.parametrize("chave", ["pendente-X", "u:pendente-X", "a:pendente-X", "Ｐendente-é", "PENDENTE-X", " pendente-X ", "x" * 80])
@pytest.mark.parametrize("lote", [False, True])
def test_prefixo_cliente_inclusive_lote(cliente, pendente, relogio, monkeypatch, chave, lote):
    from app.repositories import get_repository
    dono, n, _, _, oid = pendente
    chave = chave.replace("X", str(oid))
    repo = get_repository()
    destino = repo.obter_conta(repo.obter_pendente(oid)["payload"]["destino_carteira_id"])
    item = {"destino": conta_ref(destino["numero"]), "valor": "3000", "idempotency_key": chave}
    if lote:
        r = cliente.post("/pagamentos/lote", headers=dono.h(n), json={"itens": [item], "biometria": dono.prova()})
    else:
        r = dono.transferir(item["destino"], 3000, conta=n, idempotency_key=chave, biometria=dono.prova())
    assert r.status_code == 200, r.text
    assert [k.split(":", 1)[1] for k in _chaves()] == [f"u:{chave if lote else chave.strip()}"]
    with monkeypatch.context() as m:
        _cai_antes_do_movimento(m)
        with pytest.raises(RuntimeError, match="processo caiu"):
            _decidir(cliente, dono, n, oid)
    _rodar_job(cliente, relogio, 11)
    assert _status(cliente, dono, n, oid)["status"] == "falhou"


@pytest.mark.parametrize("lote", [False, True])
@pytest.mark.parametrize("canal", ["corpo", "header"])
def test_chave_81_caracteres_recusada(cliente, lote, canal):
    if lote and canal == "header":
        pytest.skip("Lote tem contrato de chave por item, sem header global")
    a, b = Pessoa(cliente, "c3.longa@ex.com"), Pessoa(cliente, "c3.longa.b@ex.com")
    depositar(cliente, a.numero, 100)
    h = a.h()
    item = {"destino": conta_ref(b.numero), "valor": "10"}
    if canal == "corpo":
        item["idempotency_key"] = "x" * 81
    else:
        h["Idempotency-Key"] = "x" * 81
    r = cliente.post("/pagamentos/lote" if lote else "/pagamentos/transferir", headers=h,
                     json={"itens": [item]} if lote else item)
    assert r.status_code in (400, 422), r.text
    assert a.saldo() == "100.00"


def test_folha_chave_cliente_nao_colide_com_derivada(cliente, folha):
    dono, n, f, _, (fid, _) = folha
    itens = [{"funcionario_id": fid}]
    r = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(n), json={"itens": itens})
    assert r.status_code == 200
    derivada = _chaves()[0].split(":", 1)[1].removeprefix("folha-").split("-f")[0]
    r = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(n), json={"itens": itens, "idempotency_key": derivada})
    assert r.status_code == 200
    assert len(set(_chaves())) == 2 and f.saldo() == "600.00"


@pytest.mark.parametrize("tipo", ["pix", "folha", "cobranca"])
@pytest.mark.parametrize("mudanca", ["valor", "destino"])
def test_pendente_mesma_chave_outro_pedido_conflita(cliente, pendente, tipo, mudanca):
    dono, n, op, _, _ = pendente
    a, b = Pessoa(cliente, "c3.a@ex.com"), Pessoa(cliente, "c3.b@ex.com")
    ids, cobs = [], []
    if tipo == "folha":
        for p in (a, b):
            r = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                             json={"nome": "Funcionario Silva", "cpf": p.cpf, "salario": "3000"})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
    if tipo == "cobranca":
        loja_n = a.abrir_empresa()["numero"]
        for valor in ("3000", "3001" if mudanca == "valor" else "3000"):
            cobs.append(_cobrar(cliente, a, loja_n, valor=valor)[0])
    def enviar(segundo):
        valor = "3001" if segundo and mudanca == "valor" else "3000"
        destino = int(segundo and mudanca == "destino")
        if tipo == "pix":
            return op.transferir(conta_ref((a, b)[destino].numero), valor, conta=n, idempotency_key="c3-intencao")
        if tipo == "folha":
            return cliente.post("/empresas/atual/folha/pagar", headers=op.h(n), json={
                "itens": [{"funcionario_id": ids[destino], "valor": valor}], "idempotency_key": "c3-intencao"})
        return cliente.post(f"/cobrancas/{cobs[int(segundo)]['txid']}/pagar", headers=op.h(n), json={"idempotency_key": "c3-intencao"})
    primeira = enviar(False)
    assert primeira.status_code == (200 if tipo == "folha" else 202), primeira.text
    segunda = enviar(True)
    assert dono.saldo(n) == "200000.00"
    assert segunda.status_code == 409, segunda.text


@pytest.mark.parametrize("estado", ["aprovada", "cancelada", "expirada"])
def test_reenvio_pendente_terminal_preserva_original(cliente, pendente, relogio, estado):
    dono, n, op, _, _ = pendente
    f = Pessoa(cliente, "c3.terminal@ex.com")
    def enviar():
        return op.transferir(conta_ref(f.numero), 3000, conta=n, idempotency_key="c3-terminal")
    oid = enviar().json()["operacao_id"]
    if estado == "expirada":
        relogio.definir(AGORA + timedelta(hours=73))
        assert cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).status_code == 200
    else:
        assert _decidir(cliente, dono if estado == "aprovada" else op, n, oid, aprovar=estado == "aprovada").status_code == 200
    r = enviar()
    assert r.status_code == 202 and r.json()["operacao_id"] == oid, r.text
    assert _status(cliente, dono, n, oid)["status"] == estado
    assert dono.saldo(n) == ("197000.00" if estado == "aprovada" else "200000.00")


@pytest.mark.parametrize("origem", ["pessoa", "pj", "outra_empresa"])
def test_cobranca_reenvio_outra_conta_nao_revela(cliente, loja, origem):
    dono, n, _ = loja
    a, b = Pessoa(cliente, "c3.pagador@ex.com"), Pessoa(cliente, "c3.intruso@ex.com")
    depositar(cliente, a.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10")
    caminho = f"/cobrancas/{c['txid']}/pagar"
    assert cliente.post(caminho, headers=a.h(), json={"idempotency_key": "c3-recibo"}).status_code == 200
    h = b.h() if origem == "pessoa" else (a if origem == "pj" else b).h((a if origem == "pj" else b).abrir_empresa()["numero"])
    r = cliente.post(caminho, headers=h, json={"idempotency_key": "c3-recibo"})
    assert r.status_code == 409 and "origem" not in r.json(), r.text


def test_cobranca_estornada_nao_recupera_pagamento_como_novo(cliente, loja):
    dono, n, _ = loja
    a = Pessoa(cliente, "c3.estorno@ex.com")
    depositar(cliente, a.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10")
    caminho = f"/cobrancas/{c['txid']}"
    assert cliente.post(caminho + "/pagar", headers=a.h(), json={"idempotency_key": "c3-estorno"}).status_code == 200
    assert cliente.post(caminho + "/estornar", headers=dono.h(n), json={}).status_code == 200
    assert cliente.post(caminho + "/pagar", headers=a.h(), json={"idempotency_key": "c3-estorno"}).status_code == 409
    assert a.saldo() == "100.00"


def test_pix_chave_pre_prefixo_nao_debita_reenvio(cliente):
    from app.db.base import SessionLocal
    from app.db.models import Transacao
    a, b = Pessoa(cliente, "c3.legado@ex.com"), Pessoa(cliente, "c3.legado.b@ex.com")
    depositar(cliente, a.numero, 100)
    primeira = a.transferir(conta_ref(b.numero), 10, idempotency_key="c3-legado")
    assert primeira.status_code == 200
    with SessionLocal() as s:
        t = s.get(Transacao, primeira.json()["id"])
        t.idempotency_key = t.idempotency_key.replace(":u:", ":", 1)
        s.commit()
    segunda = a.transferir(conta_ref(b.numero), 10, idempotency_key="c3-legado")
    assert segunda.status_code == 200
    assert segunda.json()["id"] == primeira.json()["id"] and a.saldo() == "90.00"


@pytest.mark.parametrize("parcial", [False, True])
def test_conciliar_folha_centavos_e_cadastro_alterado(cliente, pendente, relogio, monkeypatch, parcial):
    from app.db.base import SessionLocal
    from app.db.models import Funcionario
    from app.services import pagamento_service
    dono, n, op, _, _ = pendente
    fs = [Pessoa(cliente, f"c3.folha{i}@ex.com") for i in range(2)]
    novo_destino = Pessoa(cliente, "c3.folha.novo@ex.com")
    ids = []
    for f in fs:
        r = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n), json={"nome": "Funcionario Silva", "cpf": f.cpf, "salario": "1500.01"})
        assert r.status_code == 201
        ids.append(r.json()["id"])
    r = cliente.post("/empresas/atual/folha/pagar", headers=op.h(n), json={"itens": [{"funcionario_id": i} for i in ids]})
    oid = r.json()["pendente"]["id"]
    original = pagamento_service.transferir
    chamadas = []
    def cair_no_segundo(*args, **kwargs):
        chamadas.append(1)
        if len(chamadas) == 2:
            raise RuntimeError("processo caiu")
        return original(*args, **kwargs)
    with monkeypatch.context() as m:
        if parcial:
            m.setattr(pagamento_service, "transferir", cair_no_segundo)
        else:
            _cai_depois_do_movimento(m)
        with pytest.raises(RuntimeError, match="processo caiu"):
            _decidir(cliente, dono, n, oid)
    # Cadastro atual mudou; o snapshot da execução permanece autoridade da conciliação.
    with SessionLocal() as s:
        s.get(Funcionario, ids[0]).ativo = False
        s.get(Funcionario, ids[0]).cpf = novo_destino.cpf
        s.commit()
    from app.repositories import get_repository
    repo = get_repository()
    assert repo.obter_funcionario(ids[0])["conta_salario"]["carteira_id"] != repo.obter_pendente(oid)["payload"]["itens"][0]["destino_carteira_id"]
    _rodar_job(cliente, relogio, 11)
    p = _status(cliente, dono, n, oid)
    assert p["status"] == "aprovada" and p["resultado"]["parcial"] == parcial
    assert p["resultado"]["executados"] == (1 if parcial else 2)
    assert fs[0].saldo() == "1500.01" and fs[1].saldo() == ("0.00" if parcial else "1500.01")
    assert novo_destino.saldo() == "0.00"


def test_pendente_mesma_chave_empresas_diferentes(cliente, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "limite_duas_aprovacoes_reais", 1000)
    a, b = Pessoa(cliente, "c3.empresas@ex.com"), Pessoa(cliente, "c3.empresas.b@ex.com")
    ids = []
    for _ in range(2):
        n = a.abrir_empresa(porte="GRANDE")["numero"]
        depositar(cliente, n, 10000)
        r = a.transferir(conta_ref(b.numero), 3000, conta=n, idempotency_key="c3-mesma")
        assert r.status_code == 202, r.text
        ids.append(r.json()["operacao_id"])
    assert len(set(ids)) == 2


@pytest.mark.parametrize("mudar", ["valor", "destino", "nenhum"])
def test_conciliar_movimento_legado_confere_intencao(cliente, pendente, relogio, monkeypatch, mudar):
    from app.db.base import SessionLocal
    from app.db.models import Transacao
    from app.repositories import get_repository
    dono, n, _, _, oid = pendente
    repo = get_repository()
    p = repo.obter_pendente(oid)
    destino = repo.obter_conta(p["payload"]["destino_carteira_id"])
    if mudar == "destino":
        destino = {"numero": Pessoa(cliente, "c3.legado.destino@ex.com").numero}
    valor = "3000.01" if mudar == "valor" else "3000"
    r = dono.transferir(conta_ref(destino["numero"]), valor, conta=n, biometria=dono.prova(), idempotency_key=f"pendente-{oid}")
    assert r.status_code == 200, r.text
    # Estado realmente possível antes de 0f898a7: cliente usava o namespace interno.
    with SessionLocal() as s:
        t = s.get(Transacao, r.json()["id"])
        t.idempotency_key = t.idempotency_key.replace(":u:", ":", 1)
        s.commit()
    with monkeypatch.context() as m:
        _cai_antes_do_movimento(m)
        with pytest.raises(RuntimeError, match="processo caiu"):
            _decidir(cliente, dono, n, oid)
    _rodar_job(cliente, relogio, 11)
    assert _status(cliente, dono, n, oid)["status"] == "falhou"
