"""documentos_identidade.sha256: cabe "frente:verso" (64 -> 140)

Desde o documento com frente e verso obrigatórios, o hash gravado é
"<sha256 da frente>:<sha256 do verso>" (129 caracteres). No Postgres a coluna de 64
recusava e o cadastro com documento caía com 500 (o SQLite não confere tamanho).
Só aumenta a coluna: não destrutiva.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('documentos_identidade', schema=None) as batch_op:
        batch_op.alter_column('sha256', existing_type=sa.String(length=64), type_=sa.String(length=140),
                              existing_nullable=False)


def downgrade() -> None:
    # Volta a 64 só se não houver registro com frente:verso (senão o banco recusa).
    with op.batch_alter_table('documentos_identidade', schema=None) as batch_op:
        batch_op.alter_column('sha256', existing_type=sa.String(length=140), type_=sa.String(length=64),
                              existing_nullable=False)
