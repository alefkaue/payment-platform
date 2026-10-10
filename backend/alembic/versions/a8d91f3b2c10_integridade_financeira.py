"""Restrições financeiras, índices e trilhas somente de inserção.

Dados existentes inválidos interrompem a migração; nunca os corrigimos apagando
ou inventando saldos. Histórico legado sem transação fica preservado para análise.
"""
from alembic import op
import sqlalchemy as sa
from app.db.integridade_v1 import CHECKS, INDEXES, UNIQUES

revision = "a8d91f3b2c10"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dispositivos", sa.Column("removido", sa.Boolean(), nullable=False, server_default=sa.false()))
    for table, rules in CHECKS.items():
        with op.batch_alter_table(table) as batch:
            for name, sql in rules:
                batch.create_check_constraint(name, sql)
    for table, rules in UNIQUES.items():
        with op.batch_alter_table(table) as batch:
            for name, columns in rules:
                batch.create_unique_constraint(name, columns)
    for table, rules in INDEXES.items():
        for name, columns in rules:
            op.create_index(name, table, columns)
    op.create_index("uq_mfa_usado_referencia", "sessoes_mfa", ["referencia"], unique=True,
                    postgresql_where=sa.text("tipo = 'mfa_usado' AND sucesso"),
                    sqlite_where=sa.text("tipo = 'mfa_usado' AND sucesso"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION public.astro_trilha_imutavel() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $$
            BEGIN
                RAISE EXCEPTION 'Trilha de auditoria imutavel' USING ERRCODE = '23514';
            END $$;
        """)
        for table in ("historico_saldo", "logs_auditoria"):
            op.execute(f"CREATE TRIGGER trg_{table}_imutavel BEFORE UPDATE OR DELETE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.astro_trilha_imutavel()")
        op.execute("""
            CREATE FUNCTION public.astro_historico_vinculado() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $$
            BEGIN
                IF NEW.transacao_id IS NULL THEN
                    RAISE EXCEPTION 'Novo historico requer transacao' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END $$;
        """)
        op.execute("CREATE TRIGGER trg_historico_vinculado BEFORE INSERT ON public.historico_saldo FOR EACH ROW EXECUTE FUNCTION public.astro_historico_vinculado()")


def downgrade():
    op.drop_column("dispositivos", "removido")
    op.drop_index("uq_mfa_usado_referencia", table_name="sessoes_mfa")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_historico_vinculado ON public.historico_saldo")
        op.execute("DROP FUNCTION public.astro_historico_vinculado()")
        for table in ("historico_saldo", "logs_auditoria"):
            op.execute(f"DROP TRIGGER trg_{table}_imutavel ON public.{table}")
        op.execute("DROP FUNCTION public.astro_trilha_imutavel()")
    for table, rules in reversed(list(INDEXES.items())):
        for name, _ in rules:
            op.drop_index(name, table_name=table)
    for table, rules in reversed(list(UNIQUES.items())):
        with op.batch_alter_table(table) as batch:
            for name, _ in rules:
                batch.drop_constraint(name, type_="unique")
    for table, rules in reversed(list(CHECKS.items())):
        with op.batch_alter_table(table) as batch:
            for name, _ in rules:
                batch.drop_constraint(name, type_="check")
