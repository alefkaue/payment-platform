"""dispositivos: atestação da chave do aparelho (APK Android)

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-10-10 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('atestacao', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('atestacao_em', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.drop_column('atestacao_em')
        batch_op.drop_column('atestacao')
