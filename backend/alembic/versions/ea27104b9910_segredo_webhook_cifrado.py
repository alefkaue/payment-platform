"""Espaço para segredo de webhook cifrado; não converte dados sem chave externa."""
from alembic import op
import sqlalchemy as sa

revision = 'ea27104b9910'
down_revision = 'd71a9f04c2b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('webhooks') as batch:
        batch.alter_column('segredo', existing_type=sa.String(80), type_=sa.String(512), existing_nullable=False)


def downgrade():
    # Nunca truncar nem transformar ciphertext em texto puro silenciosamente.
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM webhooks WHERE length(segredo) > 80')):
        raise RuntimeError('Downgrade recusado: há segredos cifrados; preserve a versão atual.')
    with op.batch_alter_table('webhooks') as batch:
        batch.alter_column('segredo', existing_type=sa.String(512), type_=sa.String(80), existing_nullable=False)
