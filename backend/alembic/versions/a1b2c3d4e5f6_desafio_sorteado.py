"""desafio de prova de vida sorteado: coluna acao guarda "modo:passos" (até 80)

Revision ID: a1b2c3d4e5f6
Revises: f9a1b2c3d4e5
Create Date: 2026-10-09 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f9a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('desafios_biometria', schema=None) as batch_op:
        batch_op.alter_column('acao', existing_type=sa.String(length=20), type_=sa.String(length=80),
                              existing_nullable=False)


def downgrade() -> None:
    # Desafios valem 2 minutos: apagar os sorteados não afeta ninguém.
    op.execute("DELETE FROM desafios_biometria WHERE length(acao) > 20")
    with op.batch_alter_table('desafios_biometria', schema=None) as batch_op:
        batch_op.alter_column('acao', existing_type=sa.String(length=80), type_=sa.String(length=20),
                              existing_nullable=False)
