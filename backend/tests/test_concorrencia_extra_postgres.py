"""Concorrência real (Postgres) nas operações que ainda não tinham prova paralela.

Cada cenário dispara N chamadas ao mesmo tempo e confere: a operação acontece UMA vez
e a conciliação (scripts/verificar_banco.py) continua íntegra.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                                reason="precisa de Postgres (TEST_DATABASE_URL)")

from tests.helpers import Pessoa, admin_h, conta_ref, depositar, gerar_chave_nfe  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verificar_banco import CONSULTAS  # noqa: E402

N = 12


def _paralelo(fns):
    with ThreadPoolExecutor(max_workers=len(fns)) as ex:
        return list(ex.map(lambda f: f(), fns))


def _integro():
    from app.db.base import engine

    with engine.connect() as c:
        r = {k: c.scalar(text(sql)) for k, sql in CONSULTAS.items()}
    assert all(v == 0 for v in r.values()), r


def _tentar(fn):
    def chamar():
        try:
            return fn()
        except HTTPException as e:
            return e.status_code
        except ValueError:
            return "valueerror"
    return chamar


def test_estorno_simultaneo_devolve_uma_vez(cliente):
    from app.repositories import get_repository
    from app.services import cobranca_service

    dono, pagador = Pessoa(cliente, "loja.cc@ex.com"), Pessoa(cliente, "pagador.cc@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, pagador.numero, 500)
    cnpj = cliente.get("/empresas/atual", headers=dono.h(n)).json()["cnpj"]
    [c] = cliente.post("/cobrancas", headers=dono.h(n), json={
        "valor": "200.00", "nota_fiscal": {"chave": gerar_chave_nfe(cnpj), "cbs": "1.80", "ibs": "0.20"}}).json()
    assert cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pagador.h()).status_code == 200
    repo = get_repository()
    conta = {**repo.obter_conta_por_numero(n), "vinculo": {"papel": "admin", "alcada": None}}
    usuario = repo.obter_usuario_por_login(dono.email)
    res = _paralelo([_tentar(lambda: cobranca_service.estornar(repo, usuario=usuario, conta=conta, txid=c["txid"],
                                                                 ip=None)) for _ in range(N)])
    assert sum(1 for r in res if isinstance(r, dict)) == 1, res
    assert pagador.saldo() == "500.00"
    _integro()


def test_decisao_de_med_simultanea_devolve_uma_vez(cliente):
    a, b = Pessoa(cliente, "vitima.cc@ex.com"), Pessoa(cliente, "golpista.cc@ex.com")
    depositar(cliente, a.numero, 300)
    tid = a.transferir(conta_ref(b.numero), "100.00").json()["id"]
    assert cliente.post(f"/pagamentos/transacoes/{tid}/contestar", json={"motivo": "golpe"}, headers=a.h()).status_code < 300
    from app.repositories import get_repository
    from app.services import pagamento_service

    repo = get_repository()
    [med] = repo.listar_contestacoes("aberta")
    admin = repo.obter_usuario_por_login("admin@payflow.com.br")
    res = _paralelo([_tentar(lambda: pagamento_service.decidir_contestacao(
        repo, admin=admin, contestacao_id=med["id"], procedente=True, ip=None)) for _ in range(N)])
    assert sum(1 for r in res if isinstance(r, dict)) == 1, res
    assert a.saldo() == "300.00" and b.saldo() == "0.00"
    _integro()


def test_folha_reenviada_em_paralelo_paga_uma_vez(cliente):
    dono, func = Pessoa(cliente, "dono.cc@ex.com"), Pessoa(cliente, "func.cc@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, n, 5000)
    fid = cliente.post("/empresas/atual/funcionarios", headers=dono.h(n),
                       json={"nome": "Func Silva", "cpf": func.cpf, "salario": "300.00"}).json()["id"]

    def pagar():
        return cliente.post("/empresas/atual/folha/pagar", json={"itens": [{"funcionario_id": fid}]},
                            headers=dono.h(n)).status_code

    res = _paralelo([pagar for _ in range(N)])
    assert set(res) == {200}, res
    assert func.saldo() == "300.00" and dono.saldo(n) == "4700.00"
    _integro()


def test_mesma_nota_em_paralelo_vira_uma_cobranca(cliente):
    dono = Pessoa(cliente, "nota.cc@ex.com")
    n = dono.abrir_empresa()["numero"]
    cnpj = cliente.get("/empresas/atual", headers=dono.h(n)).json()["cnpj"]
    nota = {"chave": gerar_chave_nfe(cnpj), "cbs": "0.90", "ibs": "0.10"}

    def emitir():
        return cliente.post("/cobrancas", json={"valor": "100.00", "nota_fiscal": nota}, headers=dono.h(n)).status_code

    res = _paralelo([emitir for _ in range(N)])
    assert res.count(201) == 1 and res.count(409) == N - 1, res


def test_liberar_bloqueio_em_paralelo_libera_uma_vez(cliente):
    a, b = Pessoa(cliente, "a.lib@ex.com"), Pessoa(cliente, "b.lib@ex.com")
    depositar(cliente, a.numero, 5000)
    t = a.transferir(conta_ref(b.numero), "1500.00", biometria=a.prova()).json()
    assert t["status"] == "retida", t
    adm = admin_h(cliente)

    def liberar():
        return cliente.post(f"/admin/transacoes/{t['id']}/liberar", headers=adm).status_code

    res = _paralelo([liberar for _ in range(N)])
    assert res.count(200) == 1, res
    conta_b = cliente.get("/contas/atual", headers=b.h()).json()
    assert (conta_b["saldo"], conta_b["saldo_bloqueado"]) == ("1500.00", "0.00")
    _integro()
