"""Auditoria de privilégios efetivos, incluindo PUBLIC e permissões em colunas."""
from sqlalchemy import text
from app.db.permissoes import TABELAS_RUNTIME, COLUNAS_UPDATE, privilegios_tabela


def problemas_permissoes(connection) -> list[str]:
    if connection.dialect.name != 'postgresql':
        return ['runtime requer PostgreSQL']
    problemas = []
    elevado = connection.scalar(text('''
        SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
        FROM pg_roles WHERE rolname = current_user
    '''))
    membros = connection.scalar(text('''
        SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
        WHERE r.rolname = session_user
    '''))
    if elevado or membros or connection.scalar(text('SELECT current_user <> session_user')):
        problemas.append('papel administrativo ou associação a outro papel')
    if connection.scalar(text("SELECT has_database_privilege(current_user, current_database(), 'CREATE,TEMPORARY')")):
        problemas.append('criação de schemas ou tabelas temporárias')
    if connection.scalar(text('''
        SELECT count(*) FROM pg_namespace
        WHERE left(nspname, 3) <> 'pg_' AND nspname <> 'information_schema'
          AND has_schema_privilege(current_user, oid, 'CREATE')
    ''')):
        problemas.append('criação de objetos em schema')
    if connection.scalar(text('''
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_roles r ON r.oid = c.relowner
        WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema'
          AND r.rolname = current_user
    ''')):
        problemas.append('propriedade de objetos')
    publico = connection.scalar(text("""
        SELECT (
            SELECT count(*) FROM pg_database d,
                LATERAL aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
            WHERE d.datname = current_database() AND a.grantee = 0
        ) + (
            SELECT count(*) FROM pg_namespace n,
                LATERAL aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
            WHERE n.nspname = 'public' AND a.grantee = 0
        ) + (
            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
                LATERAL aclexplode(c.relacl) a
            WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema' AND a.grantee = 0
        ) + (
            SELECT count(*) FROM pg_attribute col JOIN pg_class c ON c.oid = col.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace,
                LATERAL aclexplode(col.attacl) a
            WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema' AND a.grantee = 0
        )
    """))
    if publico:
        problemas.append('acesso compartilhado via PUBLIC')
    relacoes = connection.execute(text("""
        SELECT c.oid, n.nspname, c.relname, p.privilegio,
               has_table_privilege(current_user, c.oid, p.privilegio),
               has_table_privilege(current_user, c.oid, p.privilegio || ' WITH GRANT OPTION')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
                           ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) p(privilegio)
        WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema'
    """)).all()
    encontradas = set()
    for oid, schema, tabela, privilegio, efetivo, grant in relacoes:
        conhecida = schema == 'public' and tabela in TABELAS_RUNTIME
        if conhecida:
            encontradas.add(tabela)
        permitidos = privilegios_tabela(tabela) if conhecida else ()
        if (efetivo and privilegio not in permitidos) or grant:
            problemas.append(f'permissão excessiva em {schema}.{tabela}')
        if conhecida and privilegio in permitidos and not efetivo:
            problemas.append(f'permissão necessária ausente em {tabela}')
    colunas = connection.execute(text("""
        SELECT n.nspname, c.relname, a.attname, p.privilegio,
               has_column_privilege(current_user, c.oid, a.attnum, p.privilegio),
               has_column_privilege(current_user, c.oid, a.attnum, p.privilegio || ' WITH GRANT OPTION')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('REFERENCES')) p(privilegio)
        WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema'
    """))
    for schema, tabela, nome, privilegio, autorizado, grant in colunas:
        conhecida = schema == 'public' and tabela in TABELAS_RUNTIME
        permitidos = privilegios_tabela(tabela) if conhecida else ()
        excecao = conhecida and privilegio == 'UPDATE' and nome in COLUNAS_UPDATE.get(tabela, ())
        if (autorizado and privilegio not in permitidos and not excecao) or grant:
            problemas.append(f'permissão excessiva em coluna de {schema}.{tabela}')
        if excecao and not autorizado:
            problemas.append(f'permissão necessária ausente em coluna de {tabela}')
    if encontradas != TABELAS_RUNTIME:
        problemas.append('schema da aplicação incompleto')
    if connection.scalar(text('''
        SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema'
          AND (has_function_privilege(current_user, p.oid, 'EXECUTE')
               OR p.proowner = (SELECT oid FROM pg_roles WHERE rolname = current_user))
    ''')):
        problemas.append('execução ou propriedade de rotinas da aplicação')
    sequencias = connection.execute(text("""
        SELECT c.oid, n.nspname, c.relname, p.privilegio,
               has_sequence_privilege(current_user, c.oid, p.privilegio),
               has_sequence_privilege(current_user, c.oid, p.privilegio || ' WITH GRANT OPTION'),
               EXISTS (
                   SELECT 1 FROM pg_depend d JOIN pg_class t ON t.oid = d.refobjid
                   JOIN pg_namespace nt ON nt.oid = t.relnamespace
                   WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
                     AND d.deptype IN ('a', 'i') AND nt.nspname = 'public'
                     AND t.relname = ANY(:tabelas)
               ) AS aprovada
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN (VALUES ('SELECT'), ('USAGE'), ('UPDATE')) p(privilegio)
        WHERE c.relkind = 'S' AND left(n.nspname, 3) <> 'pg_'
    """), {'tabelas': sorted(TABELAS_RUNTIME)})
    for oid, schema, nome, p, autorizado, grant, aprovada in sequencias:
        permitido = aprovada and schema == 'public' and p in ('SELECT', 'USAGE')
        if (autorizado and not permitido) or grant:
            problemas.append('permissão excessiva em sequência')
        if permitido and not autorizado:
            problemas.append('permissão necessária ausente em sequência')
    return sorted(set(problemas))


def conferir_permissoes(connection) -> None:
    problemas = problemas_permissoes(connection)
    if problemas:
        raise RuntimeError('Credencial da API fora da política de privilégio mínimo: ' + '; '.join(problemas))
