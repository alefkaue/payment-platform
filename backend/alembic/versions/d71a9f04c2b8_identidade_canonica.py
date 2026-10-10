"""CPF/CNPJ canônicos e formato nacional do celular.

Não modifica nem remove dados legados: valores incompatíveis precisam de correção
confirmada pelo titular antes de aplicar a migração.
"""
from alembic import op
from app.db.identidade_v1 import CHECKS_IDENTIDADE

revision = 'd71a9f04c2b8'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    for tabela, regras in CHECKS_IDENTIDADE.items():
        with op.batch_alter_table(tabela) as batch:
            for nome, sql in regras:
                batch.create_check_constraint(nome, sql)


def downgrade():
    for tabela, regras in reversed(list(CHECKS_IDENTIDADE.items())):
        with op.batch_alter_table(tabela) as batch:
            for nome, _ in reversed(regras):
                batch.drop_constraint(nome, type_='check')
