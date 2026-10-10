"""Concorrência financeira de verdade (SECURITY_AUDIT.md, seção de integridade).

Só roda contra Postgres (TEST_DATABASE_URL), onde o lock de linha (SELECT ... FOR
UPDATE) existe; o SQLite em memória dos outros testes serializa tudo e não prova nada.
No CI: .github/workflows/backend.yml sobe um Postgres e roda este arquivo.

O que precisa valer com N requisições ao mesmo tempo:
- saldo nunca negativo e nenhum centavo criado ou perdido (débitos == créditos);
- a mesma Idempotency-Key gera UMA transação;
- a alçada diária de um operador não estoura com pedidos simultâneos.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                                reason="precisa de Postgres (TEST_DATABASE_URL)")

from tests.helpers import Pessoa, conta_ref, depositar  # noqa: E402

N = 20


def _paralelo(fn, n=N):
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda _: fn(), range(n)))


def test_saques_simultaneos_nao_deixam_saldo_negativo(cliente):
    from app.db.models import AuthMetodo
    from app.repositories.exceptions import SaldoInsuficienteError
    from app.services.split_service import sem_split

    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 100)
    from app.repositories import get_repository

    repo = get_repository()
    origem = repo.obter_conta_por_numero(a.numero)["carteira_id"]
    destino = repo.obter_conta_por_numero(b.numero)["carteira_id"]

    def sacar():
        try:
            repo.executar_movimento(origem_id=origem, destino_id=destino, split=sem_split(Decimal("10")),
                                    tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
            return "ok"
        except SaldoInsuficienteError:
            return "sem_saldo"

    res = _paralelo(sacar)
    assert res.count("ok") == 10 and res.count("sem_saldo") == N - 10
    assert a.saldo() == "0.00" and b.saldo() == "100.00"


def test_mesma_chave_em_paralelo_gera_uma_transacao(cliente):
    a, b = Pessoa(cliente, "a@ex.com"), Pessoa(cliente, "b@ex.com")
    depositar(cliente, a.numero, 1000)
    from app.db.models import AuthMetodo
    from app.repositories import get_repository
    from app.services.split_service import sem_split

    repo = get_repository()
    origem = repo.obter_conta_por_numero(a.numero)["carteira_id"]
    destino = repo.obter_conta_por_numero(b.numero)["carteira_id"]

    def pagar():
        return repo.executar_movimento(origem_id=origem, destino_id=destino, split=sem_split(Decimal("50")),
                                       tipo="transferencia", auth_metodo=AuthMetodo.SENHA,
                                       idempotency_key=f"{origem}:mesma-chave")["id"]

    ids = _paralelo(pagar)
    assert len(set(ids)) == 1
    assert a.saldo() == "950.00"


def test_alcada_diaria_nao_estoura_em_paralelo(cliente):
    from app.repositories import get_repository
    from app.services import pagamento_service
    from tests.test_v9_seguranca import _aceitar, _convidar

    dono, op, forn = Pessoa(cliente, "dono@ex.com"), Pessoa(cliente, "op@ex.com"), Pessoa(cliente, "forn@ex.com")
    n = dono.abrir_empresa()["numero"]
    depositar(cliente, n, 100000)
    v = _convidar(cliente, dono, n, op, "operador", alcada=1000)
    _aceitar(cliente, op, v.json()["id"])
    repo = get_repository()
    conta = {**repo.obter_conta_por_numero(n), "vinculo": repo.obter_vinculo(
        repo.obter_usuario_por_login(op.email)["id"], repo.obter_conta_por_numero(n)["empresa_id"])}
    from app.deps import hash_dispositivo

    usuario = repo.obter_usuario_por_login(op.email)
    destino = repo.obter_conta_por_numero(forn.numero)
    aparelho = repo.obter_dispositivo(usuario["id"], hash_dispositivo(op.dispositivo))

    def pagar():
        r = pagamento_service.transferir(repo, usuario=usuario, conta=conta, dispositivo=aparelho, destino=destino,
                                         valor=Decimal("300"), descricao=None, mfa_resolvido=True,
                                         sem_bloqueio_cautelar=True)
        return "pendente" if "pendente" in r else "executada"

    res = _paralelo(pagar, n=10)
    # 3 x 300 = 900 cabem na alçada diária de 1000; o resto vai para aprovação
    assert res.count("executada") == 3, res
    assert dono.saldo(n) == "99100.00"
