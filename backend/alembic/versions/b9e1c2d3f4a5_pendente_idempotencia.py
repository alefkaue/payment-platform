"""Chave de idempotência na operação pendente (C2-05): reenvio não cria outra pendência.

Não destrutiva: só acrescenta a coluna (nula para as pendências antigas) e um índice
único parcial por empresa.
"""
from alembic import op
import sqlalchemy as sa

revision = "b9e1c2d3f4a5"
down_revision = "a8d91f3b2c10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operacoes_pendentes", sa.Column("idempotency_key", sa.String(length=140), nullable=True))
    op.create_index("uq_pendente_empresa_chave", "operacoes_pendentes", ["empresa_id", "idempotency_key"],
                    unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"),
                    sqlite_where=sa.text("idempotency_key IS NOT NULL"))


def downgrade():
    op.drop_index("uq_pendente_empresa_chave", table_name="operacoes_pendentes")
    with op.batch_alter_table("operacoes_pendentes") as batch:
        batch.drop_column("idempotency_key")
