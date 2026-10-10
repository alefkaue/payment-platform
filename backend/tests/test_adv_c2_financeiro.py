"""Revisão independente C2: não altera a implementação do Claude."""
import pytest

from tests.helpers import Pessoa, conta_ref, depositar, gerar_chave_nfe, desconfiar_aparelho
from tests.test_folha_idempotencia import folha  # noqa: F401
from tests.test_pj_regras_bancarias import pendente  # noqa: F401
from tests.test_conciliar_pendentes import AGORA, _rodar_job, _status, _cai_antes_do_movimento
from tests.test_pj_regras_bancarias import _decidir
from tests.test_cobrancas import _empresa, _cobrar
from tests.test_outbox_webhooks import loja, _entregas  # noqa: F401
from tests.helpers import admin_h


@pytest.mark.parametrize("valor", ["300", "3e2", "300.0"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="ACHADO C2-01: representação decimal equivalente muda a chave derivada e duplica salário")
def test_folha_valor_equivalente_nao_repete(cliente, folha, valor):
    dono, n, f, _, (fid, _) = folha
    for item in ({"funcionario_id": fid}, {"funcionario_id": fid, "valor": valor}):
        r = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(n), json={"itens": [item]})
        assert r.status_code == 200, r.text
    assert f.saldo() == "300.00"


def test_folha_mesma_chave_outra_empresa_nao_colide(cliente, folha):
    dono, n, f, _, (fid, _) = folha
    outra = dono.abrir_empresa()["numero"]
    depositar(cliente, outra, 1000)
    novo = cliente.post("/empresas/atual/funcionarios", headers=dono.h(outra),
                        json={"nome": "Funcionário Silva", "cpf": f.cpf, "salario": "300.00"}).json()["id"]
    for conta, id in ((n, fid), (outra, novo)):
        r = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(conta),
                         json={"itens": [{"funcionario_id": id}], "idempotency_key": "igual-c2-empresas"})
        assert r.status_code == 200, r.text
    assert f.saldo() == "600.00"


def test_folha_alterar_espacos_rotulo_nao_repete(cliente, folha):
    dono, n, f, _, (fid, _) = folha
    for descricao in ("Salário outubro", " Salário outubro "):
        r = cliente.post("/empresas/atual/folha/pagar", headers=dono.h(n),
                         json={"itens": [{"funcionario_id": fid}], "descricao": descricao})
        assert r.status_code == 200, r.text
    assert f.saldo() == "300.00"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="ACHADO C2-02: chave pública pendente-id permite conciliar movimento alheio como execução")
def test_conciliar_chave_publica_nao_prova_execucao(cliente, pendente, relogio, monkeypatch):
    dono, n, _, _, oid = pendente
    outro = Pessoa(cliente, "c2.isca@ex.com")
    # Movimento alheio de R$ 1, para outro destino, com chave controlada pelo cliente.
    assert dono.transferir(conta_ref(outro.numero), 1, conta=n,
                           idempotency_key=f"pendente-{oid}").status_code == 200
    with monkeypatch.context() as m:
        _cai_antes_do_movimento(m)
        with pytest.raises(RuntimeError, match="processo caiu"):
            _decidir(cliente, dono, n, oid)
    _rodar_job(cliente, relogio, 11)
    assert _status(cliente, dono, n, oid)["status"] == "falhou"
    assert dono.saldo(n) == "199999.00"


def test_conciliar_nao_confunde_empresa(cliente, pendente, relogio):
    from app.db.base import SessionLocal
    from app.db.models import OperacaoPendente
    dono, n, _, _, oid = pendente
    outra = dono.abrir_empresa()["numero"]
    depositar(cliente, outra, 100)
    f = Pessoa(cliente, "c2.outraempresa@ex.com")
    assert dono.transferir(conta_ref(f.numero), 1, conta=outra, idempotency_key=f"pendente-{oid}").status_code == 200
    with SessionLocal() as s:
        p = s.get(OperacaoPendente, oid)
        p.status, p.decidido_em = "executando", AGORA
        s.commit()
    _rodar_job(cliente, relogio, 11)
    assert _status(cliente, dono, n, oid)["status"] == "falhou"


@pytest.mark.parametrize("header", ["", pytest.param("   ", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason="ACHADO C2-03: header em branco é descartado e executa sem idempotência"))])
def test_header_vazio_nao_executa(cliente, header):
    a, b = Pessoa(cliente, "c2.header@ex.com"), Pessoa(cliente, "c2.destino@ex.com")
    depositar(cliente, a.numero, 100)
    r = cliente.post("/pagamentos/transferir", headers={**a.h(), "Idempotency-Key": header},
                     json={"destino": conta_ref(b.numero), "valor": "10"})
    assert r.status_code in (400, 422)
    assert a.saldo() == "100.00"


def test_header_em_rota_sem_contrato_nao_promete_idempotencia(cliente):
    a = Pessoa(cliente, "c2.rota@ex.com")
    assert cliente.get("/contas/atual", headers={**a.h(), "Idempotency-Key": "ignorada"}).status_code == 200


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="ACHADO C2-04: cobrança já paga retorna 409 antes de consultar a chave idempotente")
def test_cobranca_reenvio_header_retorna_mesmo_pagamento(cliente, loja):
    dono, n, _ = loja
    pf = Pessoa(cliente, "c2.cob@ex.com")
    depositar(cliente, pf.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    h = {**pf.h(), "Idempotency-Key": "c2-cob-unica"}
    primeira = cliente.post(f"/cobrancas/{c['txid']}/pagar", headers=h, json={})
    segunda = cliente.post(f"/cobrancas/{c['txid']}/pagar", headers=h, json={})
    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json()["id"] == segunda.json()["id"]
    assert pf.saldo() == "90.00" and len(_entregas(cliente, dono, n)) == 1


def test_outbox_respostas_sem_campo_interno(cliente, loja):
    dono, n, _ = loja
    pf = Pessoa(cliente, "c2.outbox@ex.com")
    depositar(cliente, pf.numero, 100)
    for _ in range(2):
        r = pf.transferir(conta_ref(n), 10, idempotency_key="c2-outbox")
        assert r.status_code == 200 and "_entregas" not in r.text
    for caminho in ("/pagamentos/transacoes", "/empresas/atual/webhooks/entregas", "/empresas/atual/pendentes"):
        r = cliente.get(caminho, headers=dono.h(n))
        assert r.status_code == 200 and "_entregas" not in r.text
    assert len(_entregas(cliente, dono, n)) == 1 and pf.saldo() == "90.00"


def test_nfe_cancelada_pode_reemitir_mas_parcela_aberta_bloqueia(cliente):
    dono, n, cnpj = _empresa(cliente)
    nota = {"chave": gerar_chave_nfe(cnpj), "cbs": "0.90", "ibs": "0.10"}
    cs = _cobrar(cliente, dono, n, valor="100.00", nota_fiscal=nota, parcelas=2, vencimento="2026-11-10")
    caminho = f"/cobrancas/{cs[0]['txid']}/cancelar"
    assert cliente.post(caminho, json={}, headers=dono.h(n)).status_code in (200, 204)
    r = cliente.post("/cobrancas", headers=dono.h(n), json={"valor": "100", "nota_fiscal": nota})
    assert r.status_code == 409
    assert cliente.post(f"/cobrancas/{cs[1]['txid']}/cancelar", json={}, headers=dono.h(n)).status_code in (200, 204)
    assert cliente.post("/cobrancas", headers=dono.h(n), json={"valor": "100", "nota_fiscal": nota}).status_code == 201


def test_sem_header_soma_teto_e_pj_tem_regra_propria(cliente):
    from tests.helpers import login
    a, b = Pessoa(cliente, "c2.semdev@ex.com"), Pessoa(cliente, "c2.semdev.b@ex.com")
    depositar(cliente, a.numero, 2000)
    token = login(cliente, a.email, "Cofre-Astro#2026")
    h = {"Authorization": f"Bearer {token}"}
    r = cliente.post("/pagamentos/transferir", headers=h, json={"destino": conta_ref(b.numero), "valor": "200"})
    assert r.status_code == 400 and a.saldo() == "2000.00"
    n = a.abrir_empresa()["numero"]
    depositar(cliente, n, 1000)
    desconfiar_aparelho(a.dispositivo)
    assert a.transferir(conta_ref(b.numero), 300, conta=n).status_code == 200


@pytest.mark.parametrize("tipo", ["pix", "folha", "cobranca"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="ACHADO C2-05: reenvio com mesma chave cria outra pendência em vez de devolver a intenção existente")
def test_reenvio_pendente_mesma_chave_nao_duplica(cliente, pendente, tipo):
    dono, n, op, _, _ = pendente
    forn = Pessoa(cliente, "c2.pendente.destino@ex.com")
    if tipo == "folha":
        fid = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                           json={"nome": "Fornecedor Silva", "cpf": forn.cpf, "salario": "3000"}).json()["id"]
    elif tipo == "cobranca":
        recebedor = forn.abrir_empresa()["numero"]
        [cob] = _cobrar(cliente, forn, recebedor, valor="3000")
    ids = []
    for _ in range(2):
        if tipo == "pix":
            r = op.transferir(conta_ref(forn.numero), 3000, conta=n, idempotency_key="c2-pendente-unica")
        elif tipo == "cobranca":
            r = cliente.post(f"/cobrancas/{cob['txid']}/pagar", headers=op.h(n), json={"idempotency_key": "c2-pendente-unica"})
        else:
            r = cliente.post("/empresas/atual/folha/pagar", headers=op.h(n),
                             json={"itens": [{"funcionario_id": fid}], "idempotency_key": "c2-pendente-unica"})
        assert r.status_code == (200 if tipo == "folha" else 202), r.text
        ids.append(r.json()["pendente"]["id"] if tipo == "folha" else r.json()["operacao_id"])
        assert "_entregas" not in r.text
    assert ids[0] == ids[1]


def test_aparelho_bloqueado_nao_movimenta(cliente):
    a, b = Pessoa(cliente, "c2.bloq@ex.com"), Pessoa(cliente, "c2.bloq.b@ex.com")
    depositar(cliente, a.numero, 100)
    ds = cliente.get("/seguranca/dispositivos", headers=a.h()).json()
    assert cliente.post(f"/seguranca/dispositivos/{ds[0]['id']}/bloquear", headers=a.h()).status_code == 200
    assert a.transferir(conta_ref(b.numero), 10).status_code == 401


def test_nfe_de_outra_empresa_nao_pode_reutilizar(cliente):
    dono, n, cnpj = _empresa(cliente)
    nota = {"chave": gerar_chave_nfe(cnpj), "cbs": "0.90", "ibs": "0.10"}
    _cobrar(cliente, dono, n, valor="100", nota_fiscal=nota)
    outra = dono.abrir_empresa()["numero"]
    r = cliente.post("/cobrancas", headers=dono.h(outra), json={"valor": "100", "nota_fiscal": nota})
    assert r.status_code == 400  # CNPJ da nota difere do emissor.


def test_automatico_empresas_somam_limite_diario(cliente, relogio, monkeypatch):
    from datetime import datetime, timezone
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "refresh_token_exp_dias", 90)
    dono, n, _ = _empresa(cliente)
    pf = Pessoa(cliente, "c2.auto@ex.com")
    depositar(cliente, pf.numero, 1000)
    assert cliente.put("/seguranca/limites", headers=pf.h(), json={"por_transacao": "100", "diurno": "150"}).status_code == 200
    outra = dono.abrir_empresa()["numero"]
    for empresa in (n, outra):
        a = cliente.post("/pix-automatico/autorizacoes", headers=dono.h(empresa), json={
            "pagador": {"numero": pf.numero}, "descricao": "Plano", "valor_maximo": "1000", "periodicidade": "mensal"}).json()
        assert cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/aceitar", headers=pf.h()).status_code == 200
        r = cliente.post(f"/pix-automatico/autorizacoes/{a['id']}/cobrancas", headers=dono.h(empresa),
                         json={"valor": "90", "parcelas": 2, "vencimento": "2026-10-10"})
        assert r.status_code == 201 and r.json()["valor"] == "90", r.text
        # O endpoint recorrente não parcela: o campo extra não reduz o valor.
    relogio.definir(datetime(2026, 10, 10, 15, tzinfo=timezone.utc))
    r = cliente.post("/admin/jobs/recorrencias", headers=admin_h(cliente))
    assert r.status_code == 200 and r.json()["pagas"] == 1, r.text
    assert pf.saldo() == "910.00"


def test_falha_ao_gravar_outbox_desfaz_movimento_real(cliente, loja, monkeypatch):
    from app.repositories.repository import Repositorio
    dono, n, _ = loja
    pf = Pessoa(cliente, "c2.rollback@ex.com")
    depositar(cliente, pf.numero, 100)
    def quebra(*args, **kwargs):
        raise RuntimeError("c2 falha do outbox")
    monkeypatch.setattr(Repositorio, "_enfileirar_webhooks", quebra)
    with pytest.raises(RuntimeError, match="c2 falha"):
        pf.transferir(conta_ref(n), 10)
    assert pf.saldo() == "100.00" and dono.saldo(n) == "0.00"
    assert _entregas(cliente, dono, n) == []


def test_queda_depois_commit_preserva_dinheiro_e_evento(cliente, loja, monkeypatch):
    from app.services import webhook_service
    dono, n, enviados = loja
    pf = Pessoa(cliente, "c2.crash@ex.com")
    depositar(cliente, pf.numero, 100)
    with monkeypatch.context() as m:
        def cair(*args, **kwargs):
            raise RuntimeError("c2 queda depois do commit")
        m.setattr(webhook_service, "entregar_agora", cair)
        with pytest.raises(RuntimeError, match="c2 queda"):
            pf.transferir(conta_ref(n), 10, idempotency_key="c2-crash-unico")
    assert pf.saldo() == "90.00" and len(_entregas(cliente, dono, n)) == 1
    assert pf.transferir(conta_ref(n), 10, idempotency_key="c2-crash-unico").status_code == 200
    for esperado in (1, 0):
        r = cliente.post("/admin/jobs/webhooks", headers=admin_h(cliente))
        assert r.json()["processadas"] == esperado
    assert len(enviados) == 1 and pf.saldo() == "90.00"


@pytest.mark.parametrize("tipo", ["estorno", "pendente"])
def test_outbox_estorno_e_pendencia_rollback(cliente, loja, monkeypatch, tipo):
    from app.repositories.repository import Repositorio
    from app.repositories import get_repository
    dono, n, _ = loja
    pf = Pessoa(cliente, "c2.atomicidade@ex.com")
    depositar(cliente, pf.numero, 100)
    [c] = _cobrar(cliente, dono, n, valor="10.00")
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", headers=pf.h(), json={}).status_code == 200
    def quebra(*args, **kwargs):
        raise RuntimeError("c2 falha atomica")
    monkeypatch.setattr(Repositorio, "_enfileirar_webhooks", quebra)
    with pytest.raises(RuntimeError, match="c2 falha"):
        if tipo == "estorno":
            cliente.post(f"/cobrancas/{c['txid']}/estornar", headers=dono.h(n), json={})
        else:
            # Repositório real da rota; permite isolar criação + evento sem rosto/alçada.
            repo = get_repository()
            conta = repo.obter_conta_por_numero(n)
            usuario = repo.obter_usuario_por_login(dono.email)
            repo.criar_pendente(empresa_id=conta["empresa_id"], tipo="transferencia", valor=10,
                                payload={}, criado_por=usuario["id"])
    assert pf.saldo() == "90.00" and dono.saldo(n) == "10.00"
    assert cliente.get(f"/cobrancas/{c['txid']}", headers=pf.h()).json()["status"] == "paga"
    assert len(_entregas(cliente, dono, n)) == 1
    assert cliente.get("/empresas/atual/pendentes", headers=dono.h(n)).json() == []
