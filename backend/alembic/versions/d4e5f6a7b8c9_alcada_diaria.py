"""vinculos: alçada diária por usuário (fracionamento) -- SECURITY_AUDIT.md A-02

Não destrutiva: a coluna nasce nula, e nula vale "igual à alçada por operação".

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-10 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('vinculos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alcada_diaria', sa.Numeric(precision=14, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('vinculos', schema=None) as batch_op:
        batch_op.drop_column('alcada_diaria')
