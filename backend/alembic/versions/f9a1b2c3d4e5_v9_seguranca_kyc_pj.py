"""v9: login 2 fatores (sessões por aparelho), KYC/KYB de documentos, equipe PJ
por convite (CPF) e porte, N aprovações, folha.

Não destrutiva. Dados existentes:
- vínculos: status = 'ativo' (ou 'revogado' se estavam inativos), cpf/nome/email
  copiados da pessoa, aceito_em = criado_em;
- empresas: representante = o admin mais antigo; kyb_status = 'pendente';
- pessoas: kyc_status = 'pendente' (precisam enviar o documento em
  POST /identidade/documentos antes de abrir empresa ou aceitar convite);
- operações pendentes: 1 aprovação necessária, nenhuma registrada;
- refresh tokens antigos ficam sem sessao_id: o access token deles não tem `sid`
  nem `dev` e expira em minutos; o refresh antigo continua renovando até vencer.

Revision ID: f9a1b2c3d4e5
Revises: e4f5a6b7c8d9
Create Date: 2026-10-09 19:45:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f9a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONTipo = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    """Upgrade schema."""
    # ---------------------------------------------------------------- tabelas novas
    op.create_table('documentos_empresa',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('tamanho', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('verificacoes', JSONTipo, nullable=True),
    sa.Column('enviado_por_usuario_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['enviado_por_usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('documentos_empresa', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documentos_empresa_empresa_id'), ['empresa_id'], unique=False)

    op.create_table('funcionarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('cpf', sa.String(length=11), nullable=False),
    sa.Column('cargo', sa.String(length=80), nullable=True),
    sa.Column('salario', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('desligado_em', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['criado_por_usuario_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('empresa_id', 'cpf', name='uq_funcionario_empresa_cpf')
    )
    with op.batch_alter_table('funcionarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_funcionarios_empresa_id'), ['empresa_id'], unique=False)

    op.create_table('kyc_casos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('empresa_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=4), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('nivel_risco', sa.String(length=8), nullable=False),
    sa.Column('motivos', JSONTipo, nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('concluido_em', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('kyc_casos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_kyc_casos_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_kyc_casos_usuario_id'), ['usuario_id'], unique=False)

    op.create_table('documentos_identidade',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('caso_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=12), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('provedor', sa.String(length=20), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('campos', JSONTipo, nullable=True),
    sa.Column('verificacoes', JSONTipo, nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['caso_id'], ['kyc_casos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('documentos_identidade', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documentos_identidade_caso_id'), ['caso_id'], unique=False)

    # ---------------------------------------------------------------- colunas novas
    # NOT NULL com server_default: as tabelas já têm linhas em produção.
    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bloqueado', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('bloqueado_em', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('representante_usuario_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('kyb_status', sa.String(length=12), nullable=False, server_default='pendente'))
        batch_op.create_foreign_key('fk_empresas_representante_usuario_id', 'usuarios',
                                    ['representante_usuario_id'], ['id'])

    with op.batch_alter_table('logs_auditoria', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usuario_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('empresa_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_logs_auditoria_criado_em'), ['criado_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_logs_auditoria_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_logs_auditoria_usuario_id'), ['usuario_id'], unique=False)
        batch_op.create_foreign_key('fk_logs_auditoria_empresa_id', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_foreign_key('fk_logs_auditoria_usuario_id', 'usuarios', ['usuario_id'], ['id'])

    with op.batch_alter_table('operacoes_pendentes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('descricao', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('aprovacoes_necessarias', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('aprovacoes', JSONTipo, nullable=True))

    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sessao_id', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('dispositivo_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('ip', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('user_agent', sa.String(length=200), nullable=True))
        batch_op.create_index(batch_op.f('ix_refresh_tokens_sessao_id'), ['sessao_id'], unique=False)
        batch_op.create_foreign_key('fk_refresh_tokens_dispositivo_id', 'dispositivos', ['dispositivo_id'], ['id'])

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_nascimento', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('celular', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('kyc_status', sa.String(length=12), nullable=False, server_default='pendente'))

    with op.batch_alter_table('vinculos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpf', sa.String(length=11), nullable=True))
        batch_op.add_column(sa.Column('nome', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column('celular', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('cargo', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=12), nullable=False, server_default='ativo'))
        batch_op.add_column(sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('aceito_em', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('status_em', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ultimo_acesso_em', sa.DateTime(timezone=True), nullable=True))
        # Convite ainda não aceito não tem pessoa (ela pode nem ter conta).
        batch_op.alter_column('usuario_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_index(batch_op.f('ix_vinculos_cpf'), ['cpf'], unique=False)
        batch_op.create_foreign_key('fk_vinculos_criado_por_usuario_id', 'usuarios', ['criado_por_usuario_id'], ['id'])

    # ---------------------------------------------------------------- dados existentes
    # SQL portável (Postgres e SQLite): subconsultas correlacionadas.
    op.execute("UPDATE vinculos SET status = CASE WHEN ativo THEN 'ativo' ELSE 'revogado' END, "
               "aceito_em = criado_em, status_em = criado_em")
    op.execute("UPDATE vinculos SET "
               "cpf = (SELECT u.cpf FROM usuarios u WHERE u.id = vinculos.usuario_id), "
               "nome = (SELECT u.nome FROM usuarios u WHERE u.id = vinculos.usuario_id), "
               "email = (SELECT u.email FROM usuarios u WHERE u.id = vinculos.usuario_id) "
               "WHERE usuario_id IS NOT NULL")
    op.execute("UPDATE empresas SET representante_usuario_id = ("
               "SELECT v.usuario_id FROM vinculos v WHERE v.empresa_id = empresas.id AND v.papel = 'ADMIN' "
               "ORDER BY v.criado_em, v.id LIMIT 1)")

    # A unique (empresa, cpf) só depois de preencher o cpf.
    with op.batch_alter_table('vinculos', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_vinculo_empresa_cpf', ['empresa_id', 'cpf'])


def downgrade() -> None:
    """Downgrade schema. Convites ainda não aceitos (sem pessoa) são apagados:
    a v7 exige usuario_id."""
    op.execute("DELETE FROM vinculos WHERE usuario_id IS NULL")
    op.execute("UPDATE vinculos SET ativo = CASE WHEN status = 'ativo' THEN TRUE ELSE FALSE END")

    with op.batch_alter_table('vinculos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_vinculos_criado_por_usuario_id', type_='foreignkey')
        batch_op.drop_constraint('uq_vinculo_empresa_cpf', type_='unique')
        batch_op.drop_index(batch_op.f('ix_vinculos_cpf'))
        batch_op.alter_column('usuario_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('ultimo_acesso_em')
        batch_op.drop_column('status_em')
        batch_op.drop_column('aceito_em')
        batch_op.drop_column('criado_por_usuario_id')
        batch_op.drop_column('status')
        batch_op.drop_column('cargo')
        batch_op.drop_column('celular')
        batch_op.drop_column('email')
        batch_op.drop_column('nome')
        batch_op.drop_column('cpf')

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('kyc_status')
        batch_op.drop_column('celular')
        batch_op.drop_column('data_nascimento')

    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('fk_refresh_tokens_dispositivo_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_sessao_id'))
        batch_op.drop_column('user_agent')
        batch_op.drop_column('ip')
        batch_op.drop_column('dispositivo_id')
        batch_op.drop_column('sessao_id')

    with op.batch_alter_table('operacoes_pendentes', schema=None) as batch_op:
        batch_op.drop_column('aprovacoes')
        batch_op.drop_column('aprovacoes_necessarias')
        batch_op.drop_column('descricao')

    with op.batch_alter_table('logs_auditoria', schema=None) as batch_op:
        batch_op.drop_constraint('fk_logs_auditoria_usuario_id', type_='foreignkey')
        batch_op.drop_constraint('fk_logs_auditoria_empresa_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_logs_auditoria_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_logs_auditoria_empresa_id'))
        batch_op.drop_index(batch_op.f('ix_logs_auditoria_criado_em'))
        batch_op.drop_column('empresa_id')
        batch_op.drop_column('usuario_id')

    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_empresas_representante_usuario_id', type_='foreignkey')
        batch_op.drop_column('kyb_status')
        batch_op.drop_column('representante_usuario_id')

    with op.batch_alter_table('dispositivos', schema=None) as batch_op:
        batch_op.drop_column('bloqueado_em')
        batch_op.drop_column('bloqueado')

    with op.batch_alter_table('documentos_identidade', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documentos_identidade_caso_id'))
    op.drop_table('documentos_identidade')
    with op.batch_alter_table('kyc_casos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_kyc_casos_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_kyc_casos_empresa_id'))
    op.drop_table('kyc_casos')
    with op.batch_alter_table('funcionarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_funcionarios_empresa_id'))
    op.drop_table('funcionarios')
    with op.batch_alter_table('documentos_empresa', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documentos_empresa_empresa_id'))
    op.drop_table('documentos_empresa')
