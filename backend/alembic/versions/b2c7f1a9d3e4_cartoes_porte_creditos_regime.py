"""cartoes + porte/regime (usuarios) + creditos (carteiras)

Alinha o schema ao frontend do banco digital:
- usuarios.porte (MEI|PME|GRANDE) e usuarios.regime_tributario (padrao|reduzido_30|
  reduzido_60|zero) — porte decide a verificação (biometria x e-CNPJ); regime
  define a alíquota efetiva do setor (split por negócio).
- carteiras.creditos — crédito de IBS/CBS acumulado, abatido no split inteligente.
- tabela cartoes — cartão virtual (estado + travas de segurança + limite).

Revision ID: b2c7f1a9d3e4
Revises: d5de030077b2
Create Date: 2026-10-06 12:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c7f1a9d3e4"
down_revision: Union[str, Sequence[str], None] = "d5de030077b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("porte", sa.String(length=10), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column(
            "regime_tributario",
            sa.String(length=20),
            nullable=False,
            server_default="padrao",
        ),
    )
    op.add_column(
        "carteiras",
        sa.Column("creditos", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
    )

    op.create_table(
        "cartoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("carteira_id", sa.Integer(), nullable=False),
        sa.Column("apelido", sa.String(length=60), nullable=False, server_default="Cartão virtual"),
        sa.Column("numero_masc", sa.String(length=32), nullable=False),
        sa.Column("bandeira", sa.String(length=20), nullable=False, server_default="Visa"),
        sa.Column("validade", sa.String(length=5), nullable=False),
        sa.Column("virtual", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("estado", sa.String(length=12), nullable=False, server_default="ativo"),
        sa.Column("compras_online", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "compras_internacionais", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("limite", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["carteira_id"], ["carteiras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cartoes_carteira_id", "cartoes", ["carteira_id"])


def downgrade() -> None:
    op.drop_index("ix_cartoes_carteira_id", table_name="cartoes")
    op.drop_table("cartoes")
    op.drop_column("carteiras", "creditos")
    op.drop_column("usuarios", "regime_tributario")
    op.drop_column("usuarios", "porte")
