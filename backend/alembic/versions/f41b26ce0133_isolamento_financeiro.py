"""Isolamento de saldos e ledger; consulta de destinatário sem dados financeiros."""
from alembic import op
import sqlalchemy as sa
revision = 'f41b26ce0133'
down_revision = 'f31a15bd9022'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    ctx = 'public.astro_contexto()'
    uid = f"({ctx}->>'usuario_id')::integer"
    usuario = f"({ctx}->>'modo'='usuario')"
    comum = f"({ctx}->>'modo'='sistema' OR ({usuario} AND EXISTS(SELECT 1 FROM public.usuarios u WHERE u.id={uid} AND u.ativo AND u.papel::text='ADMIN')))"
    def propria(alias):
        return f"({usuario} AND ({alias}.usuario_id={uid} OR EXISTS(SELECT 1 FROM public.vinculos v WHERE v.empresa_id={alias}.empresa_id AND v.usuario_id={uid} AND v.ativo AND v.status='ativo')))"
    def participa(colunas):
        return f"EXISTS(SELECT 1 FROM public.carteiras c WHERE c.id IN ({colunas}) AND {propria('c')})"
    role = conn.scalar(sa.text("SELECT rolname FROM pg_roles WHERE oid=(SELECT relowner FROM pg_class WHERE oid='public.carteiras'::regclass)"))
    for tabela in ['carteiras', 'transacoes', 'historico_saldo']:
        op.execute(f'ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{tabela} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY astro_migracao ON public.{tabela} TO {conn.dialect.identifier_preparer.quote(role)} USING (true) WITH CHECK (true)')
    scope = f"({ctx}->'carteiras_operacao' @> jsonb_build_array(carteiras.id))"
    nova = f"(({ctx}->>'modo'='publico' AND titular_tipo::text='PF' AND EXISTS(SELECT 1 FROM public.usuarios u WHERE u.id=carteiras.usuario_id AND u.xmin::text=txid_current()::text)) OR ({usuario} AND EXISTS(SELECT 1 FROM public.empresas e WHERE e.id=carteiras.empresa_id AND e.representante_usuario_id={uid} AND e.xmin::text=txid_current()::text)))"
    op.execute(f'CREATE POLICY astro_saldo ON public.carteiras FOR SELECT USING ({comum} OR {propria("carteiras")} OR {scope} OR {nova})')
    op.execute(f'CREATE POLICY astro_carteira_nova ON public.carteiras FOR INSERT WITH CHECK ({comum} OR {nova})')
    # Alterar saldo exige escopo de operação, inclusive para a carteira do próprio titular.
    op.execute(f'CREATE POLICY astro_movimento ON public.carteiras FOR UPDATE USING ({comum} OR {scope}) WITH CHECK ({comum} OR {scope})')
    tx = participa('transacoes.origem_carteira_id,transacoes.destino_carteira_id')
    op.execute(f'CREATE POLICY astro_transacao ON public.transacoes USING ({comum} OR {tx}) WITH CHECK ({comum} OR {tx})')
    hist = participa('historico_saldo.carteira_id')
    op.execute(f"CREATE POLICY astro_extrato ON public.historico_saldo FOR SELECT USING ({comum} OR {hist} OR ({ctx}->'carteiras_operacao' @> jsonb_build_array(carteira_id)))")
    op.execute(f"CREATE POLICY astro_ledger ON public.historico_saldo FOR INSERT WITH CHECK ({comum} OR ({ctx}->'carteiras_operacao' @> jsonb_build_array(carteira_id)))")
    op.execute('''CREATE FUNCTION public.astro_destinatario(p_id integer, p_numero text, p_agencia text, p_sistema text, p_usuario integer)
        RETURNS TABLE(id integer,titular_tipo text,usuario_id integer,empresa_id integer,sistema text,agencia text,numero text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        SELECT c.id,c.titular_tipo::text,c.usuario_id,c.empresa_id,c.sistema,c.agencia,c.numero
        FROM public.carteiras c
        WHERE public.astro_contexto()->>'modo' IN ('usuario','sistema')
          AND num_nonnulls(p_id,p_numero,p_sistema,p_usuario)=1
          AND ((p_id IS NOT NULL AND c.id=p_id) OR (p_numero IS NOT NULL AND c.numero=p_numero AND c.agencia=p_agencia)
            OR (p_sistema IS NOT NULL AND c.sistema=p_sistema) OR (p_usuario IS NOT NULL AND c.usuario_id=p_usuario AND c.titular_tipo::text='PF'))
        LIMIT 1 $$''')
    op.execute('REVOKE ALL ON FUNCTION public.astro_destinatario(integer,text,text,text,integer) FROM PUBLIC')


def downgrade():
    raise RuntimeError('Reversão recusada: removeria o isolamento de saldos e extratos.')
