"""Políticas reais em PostgreSQL migrado, com a credencial runtime restrita."""
import base64
import hashlib
import os
import secrets
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from app.db.isolamento import contexto_teste, aplicar_contexto
from app.db.models import Dispositivo,RefreshToken,AuthMetodo,RegimeApuracao,Limite
from app.repositories.repository import Repositorio

pytestmark=pytest.mark.skipif(not os.environ.get('TEST_RUNTIME_DATABASE_URL'),reason='requer PostgreSQL isolado migrado')

@pytest.fixture
def banco():
    engine=create_engine(os.environ['TEST_RUNTIME_DATABASE_URL'],hide_parameters=True,pool_size=1,max_overflow=2)
    repo=Repositorio(sessionmaker(bind=engine,expire_on_commit=False,autoflush=False))
    prefixo=secrets.token_hex(6)
    with contexto_teste(sistema=True):
        with repo._sf() as s:
            assert s.scalar(text("SELECT public.astro_contexto()->>'modo'")) == "sistema"
        a=repo.criar_pessoa(nome='Pessoa A fictícia',email=prefixo+'a@ex.com',cpf=None,senha_hash='teste',embedding_cifrado=None,
                            limites_padrao={'por_transacao':100,'diurno':100,'noturno':100})
        b=repo.criar_pessoa(nome='Pessoa B fictícia',email=prefixo+'b@ex.com',cpf=None,senha_hash='teste',embedding_cifrado=None,
                            limites_padrao={'por_transacao':100,'diurno':100,'noturno':100})
        da=repo.registrar_dispositivo(usuario_id=a['usuario_id'],id_hash=hashlib.sha256((prefixo+'a').encode()).hexdigest(),nome='Fictício A')
        db=repo.registrar_dispositivo(usuario_id=b['usuario_id'],id_hash=hashlib.sha256((prefixo+'b').encode()).hexdigest(),nome='Fictício B')
        for pessoa,dispositivo in [(a,da),(b,db)]:
            repo.salvar_refresh(usuario_id=pessoa['usuario_id'],jti=secrets.token_hex(16),token_hash=secrets.token_hex(32),
                expira_em=datetime.now(timezone.utc)+timedelta(hours=1),sessao_id=secrets.token_hex(16),dispositivo_id=dispositivo['id'],ip=None,user_agent=None)
    yield engine,repo,a,b,da,db
    engine.dispose()


def test_sem_prova_negado_e_guc_nao_autoriza(banco):
    engine,repo,a,b,da,db=banco
    with engine.begin() as conn:
        assert conn.scalar(text('SELECT count(*) FROM dispositivos'))==0
        conn.execute(text("SELECT set_config('astro.contexto',:ctx,true),set_config('astro.prova',repeat('a',64),true)"),
                     {'ctx':'{"modo":"sistema"}'})
        assert conn.scalar(text('SELECT public.astro_contexto()')) is None
        assert conn.scalar(text('SELECT count(*) FROM dispositivos'))==0
    with engine.connect() as conn,pytest.raises(DBAPIError):
        conn.execute(text('SELECT chave FROM astro_privado.contexto_chave'))


def test_titular_nao_le_nem_altera_dispositivo_de_outro(banco):
    engine,repo,a,b,da,db=banco
    with contexto_teste(a['usuario_id']),repo._sf() as s:
        assert s.get(Dispositivo,da['id']) is not None
        assert s.get(Dispositivo,db['id']) is None
        assert s.execute(text('UPDATE dispositivos SET bloqueado=true WHERE id=:id'),{'id':db['id']}).rowcount==0
        s.commit()
    with contexto_teste(a['usuario_id']):
        assert repo.bloquear_dispositivo(a['usuario_id'],db['id']) is None
    with contexto_teste(b['usuario_id']):
        assert repo.dispositivo_por_id(db['id'])['bloqueado'] is False


def test_insert_outro_titular_bloqueado_e_refresh_filtrado(banco):
    engine,repo,a,b,da,db=banco
    with contexto_teste(a['usuario_id']),repo._sf() as s:
        rows=list(s.scalars(select(RefreshToken)))
        assert rows and all(r.usuario_id==a['usuario_id'] for r in rows)
        assert s.scalar(select(Limite).where(Limite.carteira_id==b['carteira_id'])) is None
    with contexto_teste(a['usuario_id']),pytest.raises(DBAPIError):
        repo.registrar_dispositivo(usuario_id=b['usuario_id'],id_hash=secrets.token_hex(32),nome='Tentativa indevida')


def test_pool_nao_vaza_contexto_e_prova_nao_reutiliza(banco):
    engine,repo,a,b,da,db=banco
    with contexto_teste(a['usuario_id']),engine.begin() as conn:
        aplicar_contexto(conn)
        corpo=conn.scalar(text("SELECT current_setting('astro.contexto')"))
        prova=conn.scalar(text("SELECT current_setting('astro.prova')"))
        assert conn.scalar(text('SELECT count(*) FROM dispositivos WHERE id=:id'),{'id':da['id']})==1
    with engine.begin() as conn:
        assert conn.scalar(text('SELECT count(*) FROM dispositivos'))==0
        conn.execute(text("SELECT set_config('astro.contexto',:ctx,true),set_config('astro.prova',:prova,true)"),{'ctx':corpo,'prova':prova})
        assert conn.scalar(text('SELECT public.astro_contexto()')) is None
    with contexto_teste(b['usuario_id']),repo._sf() as s:
        assert s.get(Dispositivo,da['id']) is None and s.get(Dispositivo,db['id']) is not None


def test_hmac_sql_confere_com_biblioteca_padrao():
    import hmac
    engine=create_engine(os.environ['TEST_ADMIN_DATABASE_URL'],hide_parameters=True)
    try:
        with engine.connect() as conn:
            chave=bytes([33])*32
            for mensagem in [b'',b'contexto ficticio',bytes(range(256))]:
                atual=bytes(conn.scalar(text('SELECT astro_privado.hmac256(:m,:k)'),{'m':mensagem,'k':chave}))
                assert atual==hmac.new(chave,mensagem,hashlib.sha256).digest()
    finally:engine.dispose()


def test_documentos_cartoes_desafios_e_empresa_revogada(banco):
    from app.db.models import (DocumentoIdentidade, DocumentoEmpresa, CasoKyc,
                               Cartao, DesafioBiometria, Funcionario, Vinculo)
    engine,repo,a,b,da,db=banco
    with contexto_teste(sistema=True):
        empresas=[]
        for pessoa in (a,b):
            empresas.append(repo.criar_empresa(usuario_id=pessoa['usuario_id'],
                cnpj=''.join(str(secrets.randbelow(10)) for _ in range(14)),
                razao_social='Empresa fictícia '+secrets.token_hex(6), nome_fantasia=None,
                porte='MEI',regime_apuracao=RegimeApuracao.MEI,cnae=None,
                situacao_cadastral=None,verificada_por='stub'))
        ids=[]
        for pessoa,empresa in zip((a,b),empresas):
            with repo._sf() as s:
                caso=CasoKyc(usuario_id=pessoa['usuario_id'],tipo='pf',status='aprovado')
                s.add(caso);s.flush()
                doc=DocumentoIdentidade(caso_id=caso.id,tipo='rg',status='aprovado',provedor='stub',sha256=secrets.token_hex(32),campos={'nome':'Fictício'})
                dep=DocumentoEmpresa(empresa_id=empresa['empresa_id'],tipo='contrato',mime='application/pdf',tamanho=100,sha256=secrets.token_hex(32),status='aprovado')
                fun=Funcionario(empresa_id=empresa['empresa_id'],nome='Funcionário fictício',cpf='12345678901')
                card=Cartao(carteira_id=pessoa['carteira_id'],numero_masc='**** 1234',validade='12/30')
                desafio=DesafioBiometria(usuario_id=pessoa['usuario_id'],publico_id=secrets.token_hex(16),acao='ficticia',expira_em=datetime.now(timezone.utc)+timedelta(minutes=1))
                s.add_all([doc,dep,fun,card,desafio]);s.commit()
                ids.append([(type(o),o.id) for o in (doc,dep,fun,card,desafio)])
    with contexto_teste(a['usuario_id']),repo._sf() as s:
        assert all(s.get(model,id_) is not None for model,id_ in ids[0])
        assert all(s.get(model,id_) is None for model,id_ in ids[1])
        fun_b=ids[1][2][1]
        assert s.execute(text('UPDATE funcionarios SET ativo=false WHERE id=:id'),{'id':fun_b}).rowcount==0
    with contexto_teste(a['usuario_id']),repo._sf() as s,pytest.raises(DBAPIError):
        from app.db.models import PapelVinculo
        s.add(Vinculo(usuario_id=a['usuario_id'],empresa_id=empresas[1]['empresa_id'],
                      papel=PapelVinculo.ADMIN,status='ativo',ativo=True))
        s.commit()
    with contexto_teste(sistema=True),repo._sf() as s:
        v=s.scalar(select(Vinculo).where(Vinculo.usuario_id==a['usuario_id'],Vinculo.empresa_id==empresas[0]['empresa_id']))
        v.ativo=False;v.status="revogado";s.commit()
    with contexto_teste(a['usuario_id']),repo._sf() as s:
        assert s.get(Funcionario,ids[0][2][1]) is None
        assert s.get(DocumentoEmpresa,ids[0][1][1]) is None


def test_credencial_sql_nao_forja_vinculo_nem_admin(banco):
    from app.db.models import Usuario,Papel,Vinculo,PapelVinculo
    engine,repo,a,b,da,db=banco
    with engine.begin() as conn:
        assert conn.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'),{'id':a['usuario_id']}).rowcount==0
        assert conn.execute(text('UPDATE vinculos SET papel=\'ADMIN\'')).rowcount==0
    # Session assina o modo público: mesmo assim não pode criar administrador.
    from app.db.isolamento import _contexto
    token=_contexto.set({'modo':'publico','usuario_id':None})
    try:
        with repo._sf() as s,pytest.raises(DBAPIError):
            s.add(Usuario(nome='Administrador falso',email=secrets.token_hex(8)+'@ex.com',papel=Papel.ADMIN,senha_hash='teste'))
            s.commit()
    finally:_contexto.reset(token)


def test_contexto_adulterado_ou_expirado_nao_autoriza(banco):
    import json,time,hmac
    from app.core.config import get_settings
    engine,repo,a,b,da,db=banco
    with contexto_teste(a['usuario_id']),engine.begin() as conn:
        aplicar_contexto(conn)
        dados=json.loads(conn.scalar(text("SELECT current_setting('astro.contexto')")))
        dados['usuario_id']=b['usuario_id']
        conn.execute(text("SELECT set_config('astro.contexto',:corpo,true)"),{'corpo':json.dumps(dados)})
        assert conn.scalar(text('SELECT public.astro_contexto()')) is None
        assert conn.scalar(text('SELECT count(*) FROM dispositivos'))==0
        dados['exp']=int(time.time())-1
        corpo=json.dumps(dados,sort_keys=True,separators=(',',':'))
        prova=hmac.new(base64.urlsafe_b64decode(get_settings().database_context_key),corpo.encode(),hashlib.sha256).hexdigest()
        conn.execute(text("SELECT set_config('astro.contexto',:ctx,true),set_config('astro.prova',:prova,true)"),{'ctx':corpo,'prova':prova})
        assert conn.scalar(text('SELECT public.astro_contexto()')) is None


def test_cadastro_isola_casos_anonimos_e_duplicidade_nao_expoe_documento(banco):
    from app.db.models import DocumentoIdentidade
    from app.db.isolamento import _contexto
    engine,repo,a,b,da,db=banco
    resumo=secrets.token_hex(32)
    with contexto_teste(sistema=True):
        caso=repo.criar_caso_kyc(tipo='pf',status='aprovado',nivel_risco='baixo',motivos=[],usuario_id=a['usuario_id'])
        existente=repo.registrar_documento_identidade(caso_id=caso['id'],tipo='rg',status='aprovado',provedor='stub',sha256=resumo,campos={'nome':'Fictício'},verificacoes={})
    token=_contexto.set({'modo':'publico','usuario_id':None})
    try:
        assert repo.documento_ja_usado(resumo)
        with repo._sf() as s:assert s.get(DocumentoIdentidade,existente['id']) is None
        caso=repo.criar_caso_kyc(tipo='pf',status='aprovado',nivel_risco='baixo',motivos=[])
        novo=repo.registrar_documento_identidade(caso_id=caso['id'],tipo='rg',status='aprovado',provedor='stub',sha256=secrets.token_hex(32),campos={'nome':'Fictício'},verificacoes={})
        with repo._sf() as s:assert s.get(DocumentoIdentidade,novo['id']) is not None
        repo.criar_caso_kyc(tipo='pf',status='aprovado',nivel_risco='baixo',motivos=[])
        with repo._sf() as s:assert s.get(DocumentoIdentidade,novo['id']) is None
    finally:_contexto.reset(token)
    with engine.begin() as conn:
        assert conn.scalar(text('SELECT public.astro_documento_usado(:resumo)'),{'resumo':resumo}) is False


def test_saldos_extratos_e_destinatario_sem_saldo(banco):
    from decimal import Decimal
    from app.db.models import Carteira, Transacao, HistoricoSaldo
    from app.services.split_service import sem_split
    engine, repo, a, b, da, db = banco
    with contexto_teste(sistema=True):
        repo.garantir_contas_sistema()
        with repo._sf() as s:
            s.execute(text("UPDATE usuarios SET kyc_status='aprovado' WHERE id IN (:a,:b)"), {'a':a['usuario_id'], 'b':b['usuario_id']})
            s.commit()
        caixa = repo.carteira_sistema('CAIXA')
        deposito = repo.executar_movimento(origem_id=caixa['carteira_id'], destino_id=a['carteira_id'],
            split=sem_split(Decimal('50')), tipo='deposito', auth_metodo=AuthMetodo.SENHA,
            permitir_saldo_negativo=True, autor_usuario_id=None)
    with engine.begin() as conn:
        for tabela in ['carteiras', 'transacoes', 'historico_saldo']:
            assert conn.scalar(text('SELECT count(*) FROM '+tabela)) == 0
    with contexto_teste(b['usuario_id']), repo._sf() as s:
        assert s.get(Carteira, a['carteira_id']) is None
        assert s.get(Transacao, deposito['id']) is None
        assert not list(s.scalars(select(HistoricoSaldo).where(HistoricoSaldo.carteira_id == a['carteira_id'])))
        assert s.execute(text('UPDATE carteiras SET saldo=999 WHERE id=:id'), {'id':a['carteira_id']}).rowcount == 0
        assert s.execute(text('UPDATE carteiras SET saldo=999 WHERE id=:id'), {'id':b['carteira_id']}).rowcount == 0
    with contexto_teste(a['usuario_id']):
        destino = repo.buscar_destinatario(b['carteira_id'])
        assert destino['carteira_id'] == b['carteira_id']
        assert 'saldo' not in destino and 'saldo_bloqueado' not in destino
        tx = repo.executar_movimento(origem_id=a['carteira_id'], destino_id=b['carteira_id'],
            split=sem_split(Decimal('10')), tipo='transferencia', auth_metodo=AuthMetodo.SENHA,
            autor_usuario_id=a['usuario_id'], idempotency_key='rls:'+secrets.token_hex(12))
        assert tx['valor_bruto'] == Decimal('10')
        with repo._sf() as s:
            assert s.get(Carteira, b['carteira_id']) is None
        with pytest.raises(ValueError, match='sem autorização'):
            repo.executar_movimento(origem_id=b['carteira_id'], destino_id=a['carteira_id'],
                split=sem_split(Decimal('1')), tipo='transferencia', auth_metodo=AuthMetodo.SENHA,
                autor_usuario_id=a['usuario_id'])
    with contexto_teste(b['usuario_id']):
        assert repo.obter_conta(b['carteira_id'])['saldo'] == Decimal('10')
        assert repo.obter_transacao(tx['id']) is not None
        assert repo.obter_transacao(deposito['id']) is None
        # Devolução legítima permite a contraparte somente nesta sessão.
        repo.devolver_voluntario(transacao_id=tx['id'], recebedor_carteira_id=b['carteira_id'],
            valor=Decimal('2'), autor_usuario_id=b['usuario_id'], auth_metodo=AuthMetodo.SENHA,
            idempotency_key='refund:'+secrets.token_hex(12), verificacao_facial=None, prazo_dias=90)
        assert repo.obter_conta(a['carteira_id']) is None
    with contexto_teste(a['usuario_id']):
        assert repo.obter_conta(a['carteira_id'])['saldo'] == Decimal('42')


def test_concorrencia_com_rls_e_reenvio_nao_duplica(banco):
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from app.services.split_service import sem_split
    from app.repositories.exceptions import SaldoInsuficienteError
    engine, repo, a, b, da, db = banco
    with contexto_teste(sistema=True):
        repo.garantir_contas_sistema()
        with repo._sf() as s:
            s.execute(text("UPDATE usuarios SET kyc_status='aprovado' WHERE id IN (:a,:b)"), {'a':a['usuario_id'], 'b':b['usuario_id']})
            s.commit()
    with contexto_teste(a['usuario_id']):
        caixa = repo.carteira_sistema('CAIXA')
        repo.executar_movimento(origem_id=caixa['carteira_id'], destino_id=a['carteira_id'],
            split=sem_split(Decimal('12')), tipo='deposito', auth_metodo=AuthMetodo.SISTEMA,
            permitir_saldo_negativo=True)
    def pagar(chave=None):
        with contexto_teste(a['usuario_id']):
            try:
                return repo.executar_movimento(origem_id=a['carteira_id'], destino_id=b['carteira_id'],
                    split=sem_split(Decimal('3')), tipo='transferencia', auth_metodo=AuthMetodo.SENHA,
                    idempotency_key=chave)['id']
            except SaldoInsuficienteError:
                return None
    # Reenvio concorrente com a mesma chave só realiza um débito.
    chave = 'concorrente:'+secrets.token_hex(12)
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(lambda _:pagar(chave), range(8)))
    assert len(set(ids)) == 1 and ids[0] is not None
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(lambda _:pagar(), range(8)))
    assert sum(id_ is not None for id_ in ids) == 3
    with contexto_teste(a['usuario_id']):
        assert repo.obter_conta(a['carteira_id'])['saldo'] == Decimal('0')
    with contexto_teste(b['usuario_id']):
        assert repo.obter_conta(b['carteira_id'])['saldo'] == Decimal('12')
    from scripts.verificar_banco import verificar
    with engine.connect() as conn, pytest.raises(RuntimeError, match='contexto'):
        verificar(conn)
