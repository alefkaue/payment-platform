"""transacoes.idempotency_key de 80 para 200 caracteres.

Com o prefixo "u:" das chaves do cliente e o id da carteira, uma chave de 80 caracteres
passava do limite e o Postgres respondia erro 500. Só aumenta a coluna (não destrutiva).
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b9e1c2d3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transacoes") as batch:
        batch.alter_column("idempotency_key", existing_type=sa.String(length=80), type_=sa.String(length=200),
                           existing_nullable=True)


def downgrade():
    with op.batch_alter_table("transacoes") as batch:
        batch.alter_column("idempotency_key", existing_type=sa.String(length=200), type_=sa.String(length=80),
                           existing_nullable=True)
