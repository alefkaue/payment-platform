"""Estado de entregas diante de resultados atrasados e concorrentes."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.repositories import get_repository
from tests.helpers import Pessoa, conta_ref, depositar
from tests.test_outbox_webhooks import loja, _entregas  # noqa: F401


def _evento(cliente, loja):
    dono, numero, _ = loja
    pessoa = Pessoa(cliente, "estado.webhook@ex.com")
    depositar(cliente, pessoa.numero, 100)
    assert pessoa.transferir(conta_ref(numero), "1.00").status_code == 200
    [entrega] = _entregas(cliente, dono, numero)
    return get_repository(), entrega["id"]


@pytest.mark.parametrize("resultados", [(True, False), (False, True, False), (True, False, False)])
def test_sucesso_nao_e_desfeito_por_falha_atrasada(cliente, loja, resultados):
    repo, entrega_id = _evento(cliente, loja)
    for sucesso in resultados:
        repo.registrar_tentativa_entrega(entrega_id, sucesso=sucesso,
                                       resposta="HTTP 200" if sucesso else "falha de conexão",
                                       max_tentativas=2)
    entrega = repo.obter_entrega(entrega_id)
    assert entrega["status"] == "entregue"
    assert entrega["ultima_resposta"] == "HTTP 200"
    assert entrega["tentativas"] == len(resultados)
    assert repo.entregas_pendentes(10) == []


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                    reason="lock de linha exige PostgreSQL")
def test_resultados_concorrentes_nao_perdem_contagem_ou_sucesso(cliente, loja):
    repo, entrega_id = _evento(cliente, loja)
    resultados = [False] * 11 + [True]

    def registrar(sucesso):
        repo.registrar_tentativa_entrega(entrega_id, sucesso=sucesso,
                                       resposta="HTTP 200" if sucesso else "falha de conexão",
                                       max_tentativas=20)

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(registrar, resultados))
    entrega = repo.obter_entrega(entrega_id)
    assert entrega["tentativas"] == 12
    assert entrega["status"] == "entregue"
    assert entrega["ultima_resposta"] == "HTTP 200"
