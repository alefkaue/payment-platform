"""TOTP por usuário: 2º fator para pagamentos acima do limite (prompt #2)."""
from alembic import op
import sqlalchemy as sa

revision = 'a7f0c2e14d55'
down_revision = 'f41b26ce0133'
branch_labels = None
depends_on = None


def upgrade():
    # Colunas aditivas e anuláveis: seguras no banco já publicado (nenhuma linha quebra).
    op.add_column('usuarios', sa.Column('totp_segredo', sa.String(length=64), nullable=True))
    op.add_column('usuarios', sa.Column('totp_passo_usado', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('usuarios', 'totp_passo_usado')
    op.drop_column('usuarios', 'totp_segredo')
