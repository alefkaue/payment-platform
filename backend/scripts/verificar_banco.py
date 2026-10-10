"""Conciliação somente leitura: não altera saldos nem reconstrói histórico legado.
Uso: DATABASE_URL=... python scripts/verificar_banco.py
Saída contém contagens, sem CPF, e-mail ou credenciais. Exit 1 = investigar.
"""
import json
import os
import sys
from sqlalchemy import create_engine, text

CONSULTAS = {
    "historicos_sem_transacao": "SELECT count(*) FROM historico_saldo WHERE transacao_id IS NULL",
    "carteiras_negativas": "SELECT count(*) FROM carteiras WHERE saldo_bloqueado < 0 OR (saldo < 0 AND COALESCE(sistema, '') <> 'CAIXA')",
    "transacoes_desbalanceadas": """SELECT count(*) FROM (
        SELECT transacao_id FROM historico_saldo WHERE transacao_id IS NOT NULL
        GROUP BY transacao_id
        HAVING round(sum(saldo_novo - saldo_anterior + bloqueado_novo - bloqueado_anterior), 2) <> 0
    ) movimentos""",
    "carteiras_divergentes_do_historico": """WITH ultimo AS (
        SELECT carteira_id, saldo_novo, bloqueado_novo,
               row_number() OVER (PARTITION BY carteira_id ORDER BY id DESC) AS ordem
        FROM historico_saldo
    ) SELECT count(*) FROM carteiras c LEFT JOIN ultimo h ON h.carteira_id = c.id AND h.ordem = 1
    WHERE (h.carteira_id IS NULL AND (c.saldo <> 0 OR c.saldo_bloqueado <> 0))
       OR (h.carteira_id IS NOT NULL AND (c.saldo <> h.saldo_novo OR c.saldo_bloqueado <> h.bloqueado_novo))""",
    "total_financeiro": "SELECT COALESCE(sum(saldo + saldo_bloqueado), 0) FROM carteiras",
}


def verificar(connection):
    resultado = {nome: connection.scalar(text(sql)) for nome, sql in CONSULTAS.items()}
    resultado["integro"] = all(v == 0 for v in resultado.values())
    return resultado


if __name__ == "__main__":
    engine = create_engine(os.environ["DATABASE_URL"], hide_parameters=True)
    if engine.dialect.name == "postgresql":
        engine = engine.execution_options(isolation_level="REPEATABLE READ")
    with engine.connect() as connection, connection.begin():
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION READ ONLY"))
        resultado = verificar(connection)
    print(json.dumps(resultado, default=str, ensure_ascii=False))
    sys.exit(0 if resultado["integro"] else 1)
