"""Teste opcional sobre banco MIGRADO, com papel runtime de verdade.
Não usa a fixture cliente (que apaga/recria tabelas como owner).
TEST_RUNTIME_DATABASE_URL deve apontar para banco isolado provisionado em CI.
"""
import os
import secrets
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.models import AuthMetodo
from app.repositories.repository import Repositorio
from app.services.split_service import sem_split

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_RUNTIME_DATABASE_URL"), reason="requer banco migrado e credencial runtime")


def test_runtime_tem_dml_e_nao_tem_ddl_nem_alteracao_de_trilhas():
    engine = create_engine(os.environ["TEST_RUNTIME_DATABASE_URL"], hide_parameters=True)
    repo = Repositorio(sessionmaker(bind=engine, expire_on_commit=False, autoflush=False))
    repo.garantir_contas_sistema()
    conta = repo.criar_pessoa(nome="Teste runtime", email=f"runtime-{secrets.token_hex(8)}@ex.com", cpf=None,
                             senha_hash="teste-sem-login", embedding_cifrado=None)
    caixa = repo.carteira_sistema("CAIXA")
    t = repo.executar_movimento(origem_id=caixa["carteira_id"], destino_id=conta["carteira_id"],
                               split=sem_split(Decimal("10")), tipo="deposito", auth_metodo=AuthMetodo.SISTEMA,
                               permitir_saldo_negativo=True)
    repo.registrar_log(ator="teste", acao="teste_privilegios")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM historico_saldo WHERE transacao_id = :id"), {"id": t["id"]}) == 2
    for sql in (
        "CREATE TABLE public.teste_ddl_proibido(id int)",
        "UPDATE public.historico_saldo SET motivo = 'adulterado'",
        "DELETE FROM public.logs_auditoria",
        "UPDATE public.transacoes SET valor_bruto = 999",
        "DELETE FROM public.transacoes",
        "TRUNCATE public.historico_saldo",
        "SELECT * FROM public.alembic_version",
    ):
        with engine.connect() as conn, pytest.raises(DBAPIError):
            conn.execute(text(sql))
    engine.dispose()
