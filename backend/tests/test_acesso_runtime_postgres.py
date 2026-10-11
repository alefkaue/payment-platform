"""Tentativas adversariais em banco isolado migrado, nunca usando a fixture cliente."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from app.db.seguranca_runtime import conferir_permissoes

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_RUNTIME_DATABASE_URL'), reason='requer runtime PostgreSQL migrado')


@pytest.fixture
def runtime():
    engine = create_engine(os.environ['TEST_RUNTIME_DATABASE_URL'], hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def administrador():
    if not os.environ.get('TEST_ADMIN_DATABASE_URL'):
        pytest.skip('requer administrador do banco isolado')
    engine = create_engine(os.environ['TEST_ADMIN_DATABASE_URL'], hide_parameters=True)
    yield engine
    engine.dispose()


def test_runtime_aprovado(runtime, monkeypatch):
    from app.db import base
    monkeypatch.setattr(base, "engine", runtime)
    base.conferir_runtime_producao()
    with runtime.connect() as conn:
        conferir_permissoes(conn)


@pytest.mark.parametrize('sql', [
    'DELETE FROM public.usuarios',
    "UPDATE public.usuarios SET papel = 'ADMIN'",
    "UPDATE public.usuarios SET cpf = '12345678909'",
    'UPDATE public.carteiras SET usuario_id = NULL',
    'DELETE FROM public.carteiras',
    'DELETE FROM public.refresh_tokens',
    'UPDATE public.sessoes_mfa SET sucesso = true',
    'UPDATE public.documentos_identidade SET sha256 = NULL',
    'UPDATE public.creditos_tributarios SET valor = 999',
    'UPDATE public.transacoes SET autor_usuario_id = NULL',
    'CREATE TEMP TABLE teste_temporario(id int)',
    'CREATE SCHEMA teste_schema',
    'SET ROLE astro_migrator',
    'ALTER ROLE astro_app SUPERUSER',
    "SELECT pg_read_file('/etc/passwd')",
    "SET session_replication_role = replica",
    "SELECT setval('public.usuarios_id_seq', 1)",
    'SELECT public.astro_trilha_imutavel()',
])
def test_credencial_roubada_nao_permite_escalada_e_adulteracao(runtime, sql):
    with runtime.connect() as conn, pytest.raises(DBAPIError) as erro:
        conn.execute(text(sql))
    assert erro.value.orig.pgcode == "42501"  # negação de permissão, não erro de sintaxe


@pytest.mark.parametrize('conceder,revogar', [
    ('GRANT SELECT ON public.usuarios TO PUBLIC', 'REVOKE SELECT ON public.usuarios FROM PUBLIC'),
    ('GRANT UPDATE ON public.historico_saldo TO PUBLIC', 'REVOKE UPDATE ON public.historico_saldo FROM PUBLIC'),
    ('GRANT UPDATE (valor_bruto) ON public.transacoes TO astro_app', 'REVOKE UPDATE (valor_bruto) ON public.transacoes FROM astro_app'),
    ('GRANT SELECT ON public.usuarios TO astro_app WITH GRANT OPTION', 'REVOKE GRANT OPTION FOR SELECT ON public.usuarios FROM astro_app'),
    ('GRANT astro_migrator TO astro_app', 'REVOKE astro_migrator FROM astro_app'),
])
def test_boot_recusa_public_colunas_grant_option_e_membership(runtime, administrador, conceder, revogar):
    try:
        with administrador.begin() as conn:
            conn.execute(text(conceder))
        with runtime.connect() as conn, pytest.raises(RuntimeError, match='privilégio mínimo'):
            conferir_permissoes(conn)
    finally:
        with administrador.begin() as conn:
            conn.execute(text(revogar))


def test_objetos_novos_nao_ficam_publicos(runtime, administrador):
    from scripts.restringir_runtime import restringir
    try:
        with administrador.begin() as conn:
            conn.execute(text('CREATE TABLE public.segredos_futuros (id int, segredo text)'))
            conn.execute(text('GRANT SELECT (segredo) ON public.segredos_futuros TO PUBLIC'))
            conn.execute(text("CREATE FUNCTION public.escalada_teste() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"))
            conn.execute(text('GRANT EXECUTE ON FUNCTION public.escalada_teste() TO PUBLIC'))
        with runtime.connect() as conn, pytest.raises(RuntimeError):
            conferir_permissoes(conn)
        with administrador.begin() as conn:
            restringir(conn)
        with runtime.connect() as conn:
            conferir_permissoes(conn)
        for sql in ['SELECT segredo FROM public.segredos_futuros', 'SELECT public.escalada_teste()']:
            with runtime.connect() as conn, pytest.raises(DBAPIError):
                conn.execute(text(sql))
    finally:
        with administrador.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS public.segredos_futuros'))
            conn.execute(text('DROP FUNCTION IF EXISTS public.escalada_teste()'))


def test_api_cadastro_login_pix_devolucao_e_empresa_com_papel_restrito(runtime, monkeypatch):
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import main, deps
    from app.core import tempo
    from app.core.config import get_settings
    from app.repositories import repository
    from app.repositories.repository import Repositorio
    from scripts.verificar_banco import verificar
    from tests.helpers import Pessoa, conta_ref, depositar, gerar_chave_nfe
    from tests.test_cobrancas import _cobrar
    repo = Repositorio(sessionmaker(bind=runtime, expire_on_commit=False, autoflush=False))
    monkeypatch.setattr(main, 'get_repository', lambda: repo)
    monkeypatch.setattr(repository, 'usando_postgres', lambda: True)
    monkeypatch.setattr(tempo, 'agora', lambda: datetime(2026, 10, 7, 15, tzinfo=timezone.utc))
    monkeypatch.setattr(get_settings(), 'deposito_demo', True)
    main.app.dependency_overrides[deps.get_repo] = lambda: repo
    try:
        with TestClient(main.app) as cli:
            a, b = Pessoa(cli, 'integracao-runtime-a@ex.com'), Pessoa(cli, 'integracao-runtime-b@ex.com')
            depositar(cli, a.numero, 100)
            r = a.transferir(conta_ref(b.numero), '12.34', idempotency_key='runtime-pix-unico')
            assert r.status_code == 200, r.text
            assert a.transferir(conta_ref(b.numero), '12.34', idempotency_key='runtime-pix-unico').json()['id'] == r.json()['id']
            assert (a.saldo(), b.saldo()) == ('87.66', '12.34')
            dev = cli.post(f"/pagamentos/transacoes/{r.json()['id']}/devolver", headers=b.h(), json={'valor': '2.34'})
            assert dev.status_code == 201, dev.text
            assert (a.saldo(), b.saldo()) == ('90.00', '10.00')
            chave = cli.post('/pix/chaves', headers=a.h(), json={'tipo': 'aleatoria'})
            assert chave.status_code == 201, chave.text
            assert cli.delete(f"/pix/chaves/{chave.json()['id']}", headers=a.h()).status_code == 204
            pj = b.abrir_empresa()
            n = pj['numero']
            cnpj = cli.get('/empresas/atual', headers=b.h(n)).json()['cnpj']
            [c] = _cobrar(cli, b, n, valor='20.00', nota_fiscal={'chave': gerar_chave_nfe(cnpj), 'cbs': '0.18', 'ibs': '0.02'})
            paga = cli.post(f"/cobrancas/{c['txid']}/pagar", headers=a.h(), json={})
            assert paga.status_code == 200, paga.text
            assert (paga.json()['liquido'], paga.json()['imposto_total']) == ('19.80', '0.20')
            estorno = cli.post(f"/cobrancas/{c['txid']}/estornar", headers=b.h(n))
            assert estorno.status_code == 200, estorno.text
            assert a.saldo() == '90.00'
            funcionario = cli.post('/empresas/atual/funcionarios', headers=b.h(n),
                json={'nome':'Pessoa fictícia A', 'cpf':a.cpf, 'salario':'1.00'})
            assert funcionario.status_code == 201, funcionario.text
            assert funcionario.json()['conta_salario']['numero'] == a.numero
            depositar(cli, n, 10)
            folha = cli.post('/empresas/atual/folha/pagar', headers=b.h(n),
                json={'itens':[{'funcionario_id':funcionario.json()['id']}], 'idempotency_key':'runtime-folha'})
            assert folha.status_code == 200, folha.text
            assert a.saldo() == '91.00'
            from tests.helpers import login_completo,SENHA,QUADROS
            tk=login_completo(cli,a.email,SENHA,a.dispositivo)
            h={'X-Dispositivo-Id':a.dispositivo}
            renovado=cli.post('/auth/refresh',json={'refresh_token':tk['refresh_token']},headers=h)
            assert renovado.status_code==200,renovado.text
            assert cli.post('/auth/refresh',json={'refresh_token':tk['refresh_token']},headers=h).status_code==401
            assert cli.post('/auth/refresh',json={'refresh_token':renovado.json()['refresh_token']},headers=h).status_code==401
            from app.core.dados_pessoais import cifrar
            from datetime import date
            admin=create_engine(os.environ['TEST_ADMIN_DATABASE_URL'],hide_parameters=True)
            try:
                with admin.begin() as conn:
                    conn.execute(text('UPDATE usuarios SET data_nascimento=:d WHERE id=:id'),
                        {'d':cifrar(date(1990,5,17),'usuarios.data_nascimento',formato='data'),'id':repo.obter_usuario_por_email(b.email)['id']})
            finally:admin.dispose()
            h={'X-Dispositivo-Id':'aparelho-recuperacao-runtime'}
            recuperacao=cli.post('/auth/recuperacao',json={'login':b.cpf,'data_nascimento':'1990-05-17'},headers=h)
            assert recuperacao.status_code==201,recuperacao.text
            etapa=recuperacao.json()
            payload={'recuperacao_token':etapa['recuperacao_token'],'nova_senha':'NovaSenhaFicticia-2026!',
                     'biometria':{'desafio_id':etapa['desafio']['desafio_id'],'quadros':QUADROS}}
            assert cli.post('/auth/recuperacao/concluir',json=payload,headers=h).status_code==204
            assert cli.post('/auth/recuperacao/concluir',json=payload,headers=h).status_code==401
            assert cli.get('/auth/eu',headers=b.h()).status_code==401
            assert cli.post('/auth/logout', json={'refresh_token': 'invalido'}).status_code == 204
        with runtime.connect() as conn:
            from app.db.isolamento import aplicar_contexto
            aplicar_contexto(conn)
            assert verificar(conn)['integro']
            conferir_permissoes(conn)
    finally:
        main.app.dependency_overrides.pop(deps.get_repo, None)


def test_engine_aplica_timeouts_e_limite_de_pool(runtime, monkeypatch):
    from sqlalchemy.exc import TimeoutError
    from app.db import base
    from app.core.config import Settings
    s = Settings().model_copy(update={'database_url': os.environ['TEST_RUNTIME_DATABASE_URL'],
                                     'database_pool_size': 1, 'database_max_overflow': 0, 'database_pool_timeout': 1, 'ambiente': 'producao'})
    monkeypatch.setattr(base, 'get_settings', lambda: s)
    engine = base._criar_engine()
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SHOW statement_timeout")) == '15s'
            assert conn.scalar(text("SHOW lock_timeout")) == '5s'
            assert conn.scalar(text("SHOW idle_in_transaction_session_timeout")) == '30s'
            assert conn.scalar(text("SHOW search_path")) == 'pg_catalog,public'
            with pytest.raises(TimeoutError):
                engine.connect()
    finally:
        engine.dispose()


def test_reserva_e_resultado_sem_alterar_trilha_runtime(runtime):
    from sqlalchemy.orm import sessionmaker
    from app.repositories.repository import Repositorio
    import secrets
    repo = Repositorio(sessionmaker(bind=runtime))
    referencia = 'teste-runtime-' + secrets.token_hex(12)
    kwargs = dict(tipo='login', janela_min=15, limites=[(1, {'referencia': referencia})], referencia=referencia)
    reserva = repo.reservar_verificacao(**kwargs)
    assert reserva is not None
    assert repo.reservar_verificacao(**kwargs) is None
    repo.concluir_verificacao(reserva, sucesso=True)
    segunda = repo.reservar_verificacao(**kwargs)
    assert segunda is not None
    repo.concluir_verificacao(segunda, sucesso=False)
    repo.concluir_verificacao(segunda, sucesso=False)
    assert repo.reservar_verificacao(**kwargs) is None



def test_boot_recusa_runtime_dono_da_funcao_de_contexto(runtime,administrador):
    with administrador.connect() as conn:
        dono=conn.scalar(text("SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='public.astro_contexto()'::regprocedure"))
        executavel=conn.scalar(text("SELECT has_function_privilege('astro_app','public.astro_contexto()','EXECUTE')"))
    try:
        with administrador.begin() as conn:
            conn.execute(text('ALTER FUNCTION public.astro_contexto() OWNER TO astro_app'))
        with runtime.connect() as conn,pytest.raises(RuntimeError,match='rotinas'):
            conferir_permissoes(conn)
    finally:
        q=administrador.dialect.identifier_preparer.quote
        with administrador.begin() as conn:
            conn.execute(text('ALTER FUNCTION public.astro_contexto() OWNER TO '+q(dono)))
            # ALTER OWNER pode remover a ACL do dono temporário. Restaurar o
            # proprietário não repõe o GRANT explícito que a API tinha antes.
            if executavel:
                conn.execute(text('GRANT EXECUTE ON FUNCTION public.astro_contexto() TO astro_app'))
    # Regressão independente da ordem da suíte: o teste não deixa a API sem acesso.
    with runtime.connect() as conn:
        conferir_permissoes(conn)
        assert conn.scalar(text('SELECT public.astro_contexto()')) is None
