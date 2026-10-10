"""Invariantes financeiras sob uma sequência aleatória de operações (fuzz com semente fixa).

Depois de CADA operação -- válida, inválida ou no limite -- a conciliação de
scripts/verificar_banco.py tem de dar íntegro:
- a soma de todas as carteiras (CAIXA, TRIBUTOS e FISCO inclusive) é zero: dinheiro
  só nasce na CAIXA (depósito/rendimento, que ficam negativos lá) e nunca some;
- nenhuma carteira de cliente fica negativa e nenhum bloqueado fica negativo;
- toda transação fecha em zero no histórico e todo saldo bate com o último histórico.
Exceções que mudam o total de clientes (não o total geral): depósito e rendimento
saem da CAIXA; repasse de tributo vai de TRIBUTOS para o FISCO.
"""

import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.helpers import Pessoa, admin_h, conta_ref, depositar, gerar_chave_nfe

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verificar_banco import CONSULTAS  # noqa: E402

VALORES = ["0.01", "1.00", "9.99", "50.00", "123.45", "499.99", "500.00", "999.99", "1000.00", "2500.00",
           "0", "-5.00", "0.001", "1e3", "abc", "100000000000.00"]


def _conciliar() -> dict:
    from app.db.base import engine

    with engine.connect() as c:
        r = {nome: c.scalar(text(sql)) for nome, sql in CONSULTAS.items() if nome != "total_financeiro"}
        # Soma exata em Decimal (o SQLite dos testes soma NUMERIC como float; o Postgres é exato).
        r["total_financeiro"] = sum((Decimal(str(s)) + Decimal(str(b)) for s, b in
                                     c.execute(text("SELECT saldo, saldo_bloqueado FROM carteiras"))), Decimal(0))
        return r


def _assert_integro(passo: str) -> None:
    r = _conciliar()
    ruins = {k: v for k, v in r.items() if v != 0}
    assert not ruins, f"invariante quebrada depois de {passo}: {ruins}"


@pytest.mark.parametrize("semente", [7, 2026, 31337])
def test_dinheiro_nunca_nasce_nem_some(cliente, semente, monkeypatch):
    from app.routers import biometria

    # O relógio dos testes é fixo: sem isto o limite de desafios por minuto (correto) para o fuzz.
    monkeypatch.setattr(biometria, "_MAX_DESAFIOS_IP_MIN", 10_000)
    rnd = random.Random(semente)
    adm = admin_h(cliente)
    pessoas = [Pessoa(cliente, f"fuzz{semente}.{i}@ex.com") for i in range(3)]
    for p in pessoas:
        depositar(cliente, p.numero, rnd.choice(["300.00", "1500.00", "4000.00"]))
    dono = pessoas[0]
    pj = dono.abrir_empresa()["numero"]
    cnpj = cliente.get("/empresas/atual", headers=dono.h(pj)).json()["cnpj"]
    depositar(cliente, pj, "5000.00")
    _assert_integro("preparo")

    cobrancas: list[str] = []
    pagas: list[str] = []
    enviadas: list[tuple[Pessoa, int]] = []
    contas = [(p, None) for p in pessoas] + [(dono, pj)]
    feitos = 0
    ok: dict[str, int] = {}
    original = cliente.request

    def contar(*a, **k):
        r = original(*a, **k)
        if r.status_code < 300:
            ok[op] = ok.get(op, 0) + 1
        return r

    monkeypatch.setattr(cliente, "request", contar)
    for passo in range(120):
        op = rnd.choice(["pix", "pix", "pix", "pix_mesma_chave", "cobrar", "pagar", "estornar",
                         "contestar", "decidir_med", "liberar", "repassar", "rendimento"])
        try:
            if op in ("pix", "pix_mesma_chave"):
                p, conta = rnd.choice(contas)
                destino = rnd.choice([q for q in pessoas if q is not p] + ([] if conta else [None]))
                ref = conta_ref(destino.numero) if destino else conta_ref(pj)
                valor = rnd.choice(VALORES)
                extra = {}
                if op == "pix_mesma_chave":
                    extra["idempotency_key"] = f"k{rnd.randint(1, 4)}"  # repete chave, às vezes com outro valor
                if Decimal(valor) > 500 if valor.replace(".", "").isdigit() else False:
                    extra["biometria"] = p.prova()
                r = p.transferir(ref, valor, conta=conta, **extra)
                if r.status_code == 200 and r.json().get("id") and conta is None:
                    enviadas.append((p, r.json()["id"]))
            elif op == "cobrar":
                valor = rnd.choice(["10.00", "100.00", "333.33", "1200.00"])
                cbs = (Decimal(valor) * Decimal("0.009")).quantize(Decimal("0.01"))
                ibs = (Decimal(valor) * Decimal("0.001")).quantize(Decimal("0.01"))
                r = cliente.post("/cobrancas", headers=dono.h(pj), json={
                    "valor": valor, "nota_fiscal": {"chave": gerar_chave_nfe(cnpj), "cbs": str(cbs), "ibs": str(ibs)}})
                if r.status_code == 201:
                    cobrancas.extend(c["txid"] for c in r.json())
            elif op == "pagar" and cobrancas:
                txid = rnd.choice(cobrancas)
                pagador = rnd.choice(pessoas[1:])
                r = cliente.post(f"/cobrancas/{txid}/pagar", json={"biometria": pagador.prova()}, headers=pagador.h())
                if r.status_code == 200:
                    pagas.append(txid)
            elif op == "estornar" and pagas:
                cliente.post(f"/cobrancas/{rnd.choice(pagas)}/estornar", json={}, headers=dono.h(pj))
            elif op == "contestar" and enviadas:
                p, tid = rnd.choice(enviadas)
                cliente.post(f"/pagamentos/transacoes/{tid}/contestar", json={"motivo": "não reconheço"}, headers=p.h())
            elif op == "decidir_med":
                abertas = cliente.get("/admin/contestacoes", headers=adm).json()
                if abertas:
                    c = rnd.choice(abertas)
                    cliente.post(f"/admin/contestacoes/{c['id']}/decidir", json={"procedente": rnd.random() < .5},
                                 headers=adm)
            elif op == "liberar":
                cliente.post("/admin/jobs/liberar-bloqueios", headers=adm)
            elif op == "repassar":
                cliente.post("/admin/tributos/repassar", headers=adm)
            elif op == "rendimento":
                cliente.post(f"/admin/jobs/rendimento?data=2026-10-{rnd.randint(1, 7):02d}", headers=adm)
            feitos += 1
        except (KeyError, ValueError):
            pass  # resposta de erro com outro formato: a invariante abaixo é o que importa
        _assert_integro(f"passo {passo} ({op})")
    assert feitos > 60
    print(f"semente {semente}: operações com sucesso por tipo {ok}")
    # O fuzz tem de ter movido dinheiro de verdade, não só recebido erros.
    assert ok.get("pix", 0) >= 5 and ok.get("pagar", 0) >= 1 and ok.get("cobrar", 0) >= 1
    assert _conciliar()["total_financeiro"] == 0
