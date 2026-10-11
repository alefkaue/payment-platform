"""RLS com prova criptográfica; dados internos exigem contexto operacional válido."""
from alembic import op
import sqlalchemy as sa
revision='f21d04aca891'
down_revision='f01d892ca740'
branch_labels=None
depends_on=None

TABELAS = ['dispositivos','refresh_tokens','desafios_biometria','documentos_identidade',
           'documentos_empresa','funcionarios','cartoes','limites','usuarios','vinculos']


def upgrade():
    conn=op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    if conn.scalar(sa.text("SELECT to_regnamespace('astro_privado')")) is None:
        op.execute('CREATE SCHEMA astro_privado')
    op.execute('REVOKE ALL ON SCHEMA astro_privado FROM PUBLIC')
    op.execute('CREATE TABLE astro_privado.contexto_chave(id integer PRIMARY KEY CHECK(id=1), chave bytea NOT NULL CHECK(octet_length(chave)=32))')
    op.execute('REVOKE ALL ON astro_privado.contexto_chave FROM PUBLIC')
    # HMAC RFC 2104: SHA-256 é nativo do PostgreSQL; sem extensão/dependência.
    op.execute('''CREATE FUNCTION astro_privado.hmac256(mensagem bytea, chave bytea) RETURNS bytea
        LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
        DECLARE interno bytea := decode(repeat('36',64),'hex');
                externo bytea := decode(repeat('5c',64),'hex'); i integer;
        BEGIN
          IF octet_length(chave) <> 32 THEN RAISE EXCEPTION 'chave inválida'; END IF;
          FOR i IN 0..31 LOOP
            interno := set_byte(interno,i,get_byte(interno,i) # get_byte(chave,i));
            externo := set_byte(externo,i,get_byte(externo,i) # get_byte(chave,i));
          END LOOP;
          RETURN sha256(externo || sha256(interno || mensagem));
        END $$''')
    op.execute('REVOKE ALL ON FUNCTION astro_privado.hmac256(bytea,bytea) FROM PUBLIC')
    op.execute('''CREATE FUNCTION public.astro_contexto() RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,astro_privado AS $$
        DECLARE corpo text; prova text; chave bytea; esperado text; dados jsonb;
        BEGIN
          corpo := current_setting('astro.contexto',true);
          prova := current_setting('astro.prova',true);
          IF corpo IS NULL OR length(corpo)>2048 OR prova IS NULL OR length(prova)<>64 THEN RETURN NULL; END IF;
          SELECT c.chave INTO chave FROM astro_privado.contexto_chave c WHERE id=1;
          IF chave IS NULL THEN RETURN NULL; END IF;
          esperado := encode(astro_privado.hmac256(convert_to(corpo,'UTF8'),chave),'hex');
          IF sha256(convert_to(esperado,'UTF8')) <> sha256(convert_to(prova,'UTF8')) THEN RETURN NULL; END IF;
          dados := corpo::jsonb;
          IF dados->>'pid' IS NULL OR dados->>'tx' IS NULL OR dados->>'exp' IS NULL
             OR dados->>'modo' IS NULL THEN RETURN NULL; END IF;
          IF dados->>'modo'='usuario' AND (coalesce((dados->>'usuario_id')::integer,0)<1) THEN RETURN NULL; END IF;
          IF (dados->>'pid')::integer <> pg_backend_pid() OR (dados->>'tx')::bigint <> txid_current()
             OR (dados->>'exp')::bigint < extract(epoch FROM statement_timestamp())
             OR (dados->>'exp')::bigint > extract(epoch FROM statement_timestamp())+35
             OR dados->>'modo' NOT IN ('publico','usuario','sistema') THEN RETURN NULL; END IF;
          RETURN dados;
        EXCEPTION WHEN OTHERS THEN RETURN NULL;
        END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.astro_contexto() FROM PUBLIC')
    role=conn.scalar(sa.text("SELECT rolname FROM pg_roles WHERE oid=(SELECT relowner FROM pg_class WHERE oid='public.usuarios'::regclass)"))
    quote=conn.dialect.identifier_preparer.quote
    for tabela in TABELAS:
        contexto='public.astro_contexto()'
        uid=f"({contexto}->>'usuario_id')::integer"
        usuario=f"({contexto}->>'modo'='usuario')"
        comum=f"({contexto}->>'modo'='sistema' OR ({usuario} AND EXISTS(SELECT 1 FROM public.usuarios u WHERE u.id={uid} AND u.ativo AND u.papel::text='ADMIN')))"
        empresa=lambda coluna: f"({usuario} AND EXISTS(SELECT 1 FROM public.vinculos v WHERE v.empresa_id={coluna} AND v.usuario_id={uid} AND v.ativo AND v.status='ativo'))"
        if tabela in {'usuarios','vinculos'}:
            op.execute(f'ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE public.{tabela} FORCE ROW LEVEL SECURITY')
            # Autenticação e busca de destinatários precisam consultar os envelopes.
            # Somente escritas ficam restritas aqui; os 8 objetos internos filtram leitura.
            op.execute(f'CREATE POLICY astro_consulta_cifrada ON public.{tabela} FOR SELECT TO PUBLIC USING (true)')
            if tabela == 'usuarios':
                inserir=f"({comum} OR ({contexto}->>'modo'='publico' AND papel::text='USUARIO'))"
                alterar=f"({comum} OR ({usuario} AND id={uid}))"
            else:
                admin=f"({usuario} AND EXISTS(SELECT 1 FROM public.vinculos v WHERE v.empresa_id=vinculos.empresa_id AND v.usuario_id={uid} AND v.ativo AND v.status='ativo' AND v.papel::text='ADMIN'))"
                abertura=f"({usuario} AND usuario_id={uid} AND EXISTS(SELECT 1 FROM public.empresas e WHERE e.id=vinculos.empresa_id AND e.representante_usuario_id={uid} AND e.xmin::text=txid_current()::text))"
                convite=f"({usuario} AND EXISTS(SELECT 1 FROM public.usuarios u WHERE u.id={uid} AND u.cpf_indice=vinculos.cpf_indice) AND (usuario_id IS NULL OR usuario_id={uid}))"
                inserir=f'({comum} OR {admin} OR {abertura})'
                alterar=f'({comum} OR {admin} OR {convite})'
            op.execute(f'CREATE POLICY astro_cadastro ON public.{tabela} FOR INSERT TO PUBLIC WITH CHECK ({inserir})')
            op.execute(f'CREATE POLICY astro_alteracao ON public.{tabela} FOR UPDATE TO PUBLIC USING ({alterar}) WITH CHECK ({alterar})')
            op.execute(f'CREATE POLICY astro_migracao ON public.{tabela} TO {quote(role)} USING (true) WITH CHECK (true)')
            continue
        if tabela in {'dispositivos','refresh_tokens'}:
            regra=f'({usuario} AND usuario_id={uid})'
        elif tabela=='desafios_biometria':
            regra=f"(({usuario} AND usuario_id={uid}) OR ({contexto}->>'modo'='publico' AND (usuario_id IS NULL OR usuario_id=({contexto}->>'desafio_usuario_id')::integer)))"
        elif tabela in {'funcionarios','documentos_empresa'}:
            regra=empresa(tabela+'.empresa_id')
        elif tabela=='documentos_identidade':
            regra=f"EXISTS(SELECT 1 FROM public.kyc_casos k WHERE k.id=caso_id AND (({usuario} AND k.usuario_id={uid}) OR {empresa('k.empresa_id')} OR ({contexto}->>'modo'='publico' AND k.usuario_id IS NULL AND k.empresa_id IS NULL)))"
        else:
            regra=f"EXISTS(SELECT 1 FROM public.carteiras c WHERE c.id=carteira_id AND (({usuario} AND c.usuario_id={uid}) OR {empresa('c.empresa_id')}))"
        expr=f'({comum} OR ({regra}))'
        op.execute(f'ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{tabela} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY astro_titular ON public.{tabela} TO PUBLIC USING ({expr}) WITH CHECK ({expr})')
        op.execute(f'CREATE POLICY astro_migracao ON public.{tabela} TO {quote(role)} USING (true) WITH CHECK (true)')
        if tabela=='limites':
            # Cadastro público pode criar limites apenas da carteira criada nessa transação.
            op.execute(f"CREATE POLICY astro_cadastro_limite_leitura ON public.limites FOR SELECT TO PUBLIC USING ({contexto}->>'modo'='publico' AND EXISTS(SELECT 1 FROM public.carteiras c WHERE c.id=carteira_id AND c.xmin::text=txid_current()::text))")
            op.execute(f"CREATE POLICY astro_cadastro_limite ON public.limites FOR INSERT TO PUBLIC WITH CHECK ({contexto}->>'modo'='publico' AND EXISTS(SELECT 1 FROM public.carteiras c WHERE c.id=carteira_id AND c.xmin::text=txid_current()::text))")


def downgrade():
    conn=op.get_bind()
    if conn.dialect.name!='postgresql': return
    for tabela in TABELAS:
        op.execute(f'DROP POLICY IF EXISTS astro_cadastro_limite_leitura ON public.{tabela}')
        op.execute(f'DROP POLICY IF EXISTS astro_cadastro_limite ON public.{tabela}')
        if tabela in {'usuarios','vinculos'}:
            op.execute(f'DROP POLICY astro_consulta_cifrada ON public.{tabela}')
            op.execute(f'DROP POLICY astro_cadastro ON public.{tabela}')
            op.execute(f'DROP POLICY astro_alteracao ON public.{tabela}')
        else:
            op.execute(f'DROP POLICY astro_titular ON public.{tabela}')
        op.execute(f'DROP POLICY astro_migracao ON public.{tabela}')
        op.execute(f'ALTER TABLE public.{tabela} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{tabela} DISABLE ROW LEVEL SECURITY')
    op.execute('DROP FUNCTION public.astro_contexto()')
    op.execute('DROP SCHEMA astro_privado CASCADE')
