"""dpop_jtis: provas DPoP já usadas (uso único)

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-09 21:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('dpop_jtis',
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('jti')
    )
    with op.batch_alter_table('dpop_jtis', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dpop_jtis_expira_em'), ['expira_em'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('dpop_jtis', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dpop_jtis_expira_em'))
    op.drop_table('dpop_jtis')
