"""Consulta só de existência e caso de cadastro vinculado ao contexto assinado."""
from alembic import op
import sqlalchemy as sa
revision='f31a15bd9022'
down_revision='f21d04aca891'
branch_labels=None
depends_on=None


def upgrade():
    if op.get_bind().dialect.name!='postgresql':return
    op.execute('''CREATE FUNCTION public.astro_documento_usado(resumo text) RETURNS boolean
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        BEGIN
          IF public.astro_contexto() IS NULL OR resumo IS NULL OR length(resumo)>140
             OR resumo !~ '^[0-9a-f]{64}(:[0-9a-f]{64})?$' THEN RETURN false; END IF;
          RETURN EXISTS(SELECT 1 FROM public.documentos_identidade d
                        JOIN public.kyc_casos k ON k.id=d.caso_id
                        WHERE d.sha256=resumo AND k.usuario_id IS NOT NULL);
        END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.astro_documento_usado(text) FROM PUBLIC')
    op.execute('''ALTER POLICY astro_titular ON public.documentos_identidade TO PUBLIC
      USING (
        public.astro_contexto()->>'modo'='sistema'
        OR (public.astro_contexto()->>'modo'='usuario' AND EXISTS(
          SELECT 1 FROM public.usuarios u WHERE u.id=(public.astro_contexto()->>'usuario_id')::integer AND u.ativo AND u.papel::text='ADMIN'))
        OR EXISTS(SELECT 1 FROM public.kyc_casos k WHERE k.id=caso_id AND (
          (public.astro_contexto()->>'modo'='usuario' AND k.usuario_id=(public.astro_contexto()->>'usuario_id')::integer)
          OR (public.astro_contexto()->>'modo'='usuario' AND EXISTS(SELECT 1 FROM public.vinculos v WHERE v.empresa_id=k.empresa_id AND v.usuario_id=(public.astro_contexto()->>'usuario_id')::integer AND v.ativo AND v.status='ativo'))
          OR (public.astro_contexto()->>'modo'='publico' AND k.usuario_id IS NULL AND k.empresa_id IS NULL AND k.id=(public.astro_contexto()->>'kyc_caso_id')::integer)
        ))
      )''')
    # WITH CHECK omitido herda USING (política original tinha WITH CHECK explícito).
    conn=op.get_bind()
    expr=conn.scalar(sa.text("SELECT pg_get_expr(polqual,polrelid) FROM pg_policy WHERE polname='astro_titular' AND polrelid='public.documentos_identidade'::regclass"))
    op.execute('ALTER POLICY astro_titular ON public.documentos_identidade WITH CHECK ('+expr+')')


def downgrade():
    raise RuntimeError('Downgrade recusado: preserva o isolamento dos casos de cadastro. Use recuperação explícita de backup.')
