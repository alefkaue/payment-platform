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


def test_liberacoes_simultaneas_nao_creditam_duas_vezes(cliente):
    from datetime import timedelta
    from app.core import tempo
    from app.db.models import AuthMetodo
    from app.repositories import get_repository
    from app.services.split_service import sem_split
    a, b = Pessoa(cliente, "libera-a@ex.com"), Pessoa(cliente, "libera-b@ex.com")
    depositar(cliente, a.numero, 100)
    repo = get_repository()
    origem = repo.obter_conta_por_numero(a.numero)["carteira_id"]
    destino = repo.obter_conta_por_numero(b.numero)["carteira_id"]
    t = repo.executar_movimento(origem_id=origem, destino_id=destino, split=sem_split(Decimal("50")),
                               tipo="transferencia", auth_metodo=AuthMetodo.SENHA,
                               bloqueio_ate=tempo.agora() + timedelta(hours=72))
    res = _paralelo(lambda: repo.liberar_bloqueio(t["id"]), n=10)
    assert sum(r is not None for r in res) == 1
    assert b.saldo() == "50.00"


def test_devolucoes_simultaneas_nao_repetem_debito(cliente):
    from app.db.models import AuthMetodo
    from app.repositories import get_repository
    from app.services.split_service import sem_split
    a, b = Pessoa(cliente, "devolve-a@ex.com"), Pessoa(cliente, "devolve-b@ex.com")
    depositar(cliente, a.numero, 100)
    depositar(cliente, b.numero, 100)
    repo = get_repository()
    origem = repo.obter_conta_por_numero(a.numero)["carteira_id"]
    destino = repo.obter_conta_por_numero(b.numero)["carteira_id"]
    t = repo.executar_movimento(origem_id=origem, destino_id=destino, split=sem_split(Decimal("50")),
                               tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
    res = _paralelo(lambda: repo.devolver(transacao_id=t["id"], valor_maximo=Decimal("50"),
                                        tipo="devolucao", autor_usuario_id=None), n=10)
    assert sum(r["valor_devolvido"] for r in res) == 50
    assert a.saldo() == b.saldo() == "100.00"


def test_refresh_simultaneo_nao_cria_duas_sessoes_validas(cliente):
    from fastapi import HTTPException
    from app.core.security import hash_refresh
    from app.deps import hash_dispositivo
    from app.repositories import get_repository
    from app.services.auth_service import renovar
    from tests.helpers import login_completo, SENHA
    p = Pessoa(cliente, "refresh-paralelo@ex.com")
    tokens = login_completo(cliente, p.email, SENHA, p.dispositivo)
    repo = get_repository()
    registro = repo.obter_refresh(hash_refresh(tokens["refresh_token"]))

    def refresh():
        try:
            renovar(repo, refresh_token=tokens["refresh_token"], dispositivo_hash=hash_dispositivo(p.dispositivo))
            return "ok"
        except HTTPException as e:
            assert e.status_code == 401
            return "recusado"

    res = _paralelo(refresh, n=5)
    assert res.count("ok") <= 1
    # Reuso detectado encerra a família, inclusive o token emitido pela primeira chamada.
    assert not repo.sessao_ativa(registro["sessao_id"])


def test_mfa_intermediario_so_pode_ser_consumido_uma_vez(cliente):
    from app.repositories import get_repository
    repo = get_repository()
    res = _paralelo(lambda: repo.registrar_sessao_mfa(tipo="mfa_usado", sucesso=True,
                                                     referencia="mesmo-mfa-em-paralelo"), n=10)
    assert res.count(True) == 1


def test_duas_decisoes_med_nao_podem_contradizer_o_dinheiro(cliente):
    from app.db.models import AuthMetodo
    from app.repositories import get_repository
    from app.services.split_service import sem_split
    a, b = Pessoa(cliente, "med-a@ex.com"), Pessoa(cliente, "med-b@ex.com")
    depositar(cliente, a.numero, 100)
    repo = get_repository()
    ca, cb = repo.obter_conta_por_numero(a.numero), repo.obter_conta_por_numero(b.numero)
    t = repo.executar_movimento(origem_id=ca["carteira_id"], destino_id=cb["carteira_id"],
                               split=sem_split(Decimal("50")), tipo="transferencia", auth_metodo=AuthMetodo.SENHA)
    c = repo.criar_contestacao(transacao_id=t["id"], usuario_id=ca["usuario_id"], motivo="Teste concorrente")
    admin = repo.obter_usuario_por_login("admin@payflow.com.br")
    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(lambda procedente: repo.resolver_contestacao(
            c["id"], procedente=procedente, autor_usuario_id=admin["id"]), [True, False]))
    assert sum(r is not None for r in resultados) == 1
    decisao = repo.obter_contestacao(c["id"])
    if decisao["status"] == "procedente":
        assert a.saldo() == "100.00" and b.saldo() == "0.00"
    else:
        assert a.saldo() == b.saldo() == "50.00"
