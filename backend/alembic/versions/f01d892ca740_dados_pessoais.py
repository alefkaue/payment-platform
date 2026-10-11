"""Envelope cifrado, índices de igualdade e vínculo das reservas; mantém dados."""
from alembic import op
import sqlalchemy as sa

revision = 'f01d892ca740'
down_revision = 'ea27104b9910'
branch_labels = None
depends_on = None

# Snapshot desta versão: não importar um contrato que evolua com os modelos.
CAMPOS = {
 'usuarios': ['nome','cpf','email','celular','data_nascimento'],
 'empresas': ['cnpj','razao_social','nome_fantasia'],
 'vinculos': ['cpf','nome','email','celular'], 'funcionarios': ['cpf','nome'],
 'chaves_pix': ['valor'], 'cobrancas': ['pagador_documento','descricao'],
 'transacoes': ['descricao','verificacao_facial'],
 'operacoes_pendentes': ['payload','descricao','aprovacoes','resultado'],
 'autorizacoes_recorrentes': ['descricao'], 'contestacoes': ['motivo'],
 'refresh_tokens': ['ip','user_agent'], 'sessoes_mfa': ['referencia','ip','detalhe'],
 'logs_auditoria': ['ator','ip','detalhe'], 'kyc_casos': ['motivos'],
 'documentos_identidade': ['campos','verificacoes'], 'documentos_empresa': ['verificacoes'],
 'webhook_entregas': ['payload','ultima_resposta'],
}
BUSCA = {'usuarios':['cpf','email'],'empresas':['cnpj'],'vinculos':['cpf'],
         'funcionarios':['cpf'],'chaves_pix':['valor'],'sessoes_mfa':['referencia','ip']}


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    for tabela, nomes in CAMPOS.items():
        colunas = {c['name']: c for c in insp.get_columns(tabela)}
        indices = [i for i in insp.get_indexes(tabela) if not i.get('duplicates_constraint')]
        unicas = insp.get_unique_constraints(tabela)
        checks = insp.get_check_constraints(tabela)
        with op.batch_alter_table(tabela, naming_convention={'uq':'%(table_name)s_%(column_0_name)s_key'}) as batch:
            for ck in checks:
                if ck['name'] in {'ck_usuario_cpf_canonico','ck_usuario_celular_canonico','ck_empresa_cnpj_canonico'}:
                    batch.drop_constraint(ck['name'], type_='check')
            for nome in nomes:
                c = colunas[nome]
                batch.alter_column(nome, existing_type=c['type'], type_=sa.Text(), existing_nullable=c['nullable'],
                                   postgresql_using=f'"{nome}"::text')
            for nome in BUSCA.get(tabela, []):
                batch.add_column(sa.Column(nome+'_indice',sa.String(64),sa.Computed(
                    f"CASE WHEN substr({nome}, 1, 7) = 'pii:v1:' THEN substr({nome}, 8, 64) ELSE NULL END",persisted=True)))
                for uq in unicas:
                    if nome in uq['column_names']:
                        nome_uq=uq['name'] or tabela+'_'+uq['column_names'][0]+'_key'
                        batch.drop_constraint(nome_uq,type_='unique')
                        batch.create_unique_constraint(nome_uq,[nome+'_indice' if c==nome else c for c in uq['column_names']])
                for ix in indices:
                    if nome in ix['column_names']:
                        batch.drop_index(ix['name'])
                        batch.create_index(ix['name'],[nome+'_indice' if c==nome else c for c in ix['column_names']],unique=ix['unique'], **ix.get('dialect_options',{}))
    with op.batch_alter_table('sessoes_mfa') as batch:
        batch.add_column(sa.Column('reserva_id',sa.Integer(),nullable=True))
        batch.create_foreign_key('fk_mfa_reserva','sessoes_mfa',['reserva_id'],['id'])
        batch.create_index('ix_sessoes_mfa_reserva_id',['reserva_id'])
    # Conclusões de versões anteriores usavam a referência numérica em texto.

    conn.execute(sa.text("UPDATE sessoes_mfa SET reserva_id = CAST(referencia AS INTEGER) WHERE tipo IN ('login_concluido','biometria_concluido') AND referencia IS NOT NULL"))
    if conn.dialect.name == 'postgresql':
        for tabela, nomes in CAMPOS.items():
            for coluna in nomes:
                # Preserva legados até o script; novas escritas já exigem envelope.
                op.execute(f"ALTER TABLE {tabela} ADD CONSTRAINT ck_pii_{tabela}_{coluna} CHECK ({coluna} IS NULL OR (substr({coluna}, 1, 7) = 'pii:v1:' AND substr({coluna}, 72, 1) = ':' AND length({coluna}) > 170)) NOT VALID")


def downgrade():
    # Segurança e tipo dos campos mudaram. Reverter exige procedimento explícito,
    # nunca transformação automática de ciphertext em texto puro.
    raise RuntimeError('Downgrade recusado: migração de dados pessoais exige recuperação explícita de backup protegido.')
