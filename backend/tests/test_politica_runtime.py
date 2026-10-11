from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.permissoes import TABELAS_RUNTIME, TABELAS_DELETE, TABELAS_APPEND_ONLY, COLUNAS_UPDATE, privilegios_tabela


def test_toda_tabela_precisa_de_politica_explicita():
    assert TABELAS_RUNTIME == set(Base.metadata.tables)
    assert TABELAS_DELETE <= TABELAS_RUNTIME
    assert TABELAS_APPEND_ONLY <= TABELAS_RUNTIME


def test_historicos_nao_perdem_dados_e_transacao_so_muda_estado():
    for tabela in TABELAS_APPEND_ONLY | COLUNAS_UPDATE.keys():
        assert privilegios_tabela(tabela) == ('SELECT', 'INSERT')
    assert {t for t in TABELAS_RUNTIME if 'DELETE' in privilegios_tabela(t)} == {'chaves_pix', 'dpop_jtis'}


def test_engine_limita_conexoes_e_consultas(monkeypatch):
    from app.db import base
    from app.core.config import Settings
    chamadas = []
    s = Settings().model_copy(update={'database_url': 'postgresql+psycopg2://runtime:teste@localhost/isolado',
                                     'database_pool_size': 3, 'database_max_overflow': 2, 'database_pool_timeout': 4, 'ambiente': 'producao'})
    monkeypatch.setattr(base, 'get_settings', lambda: s)
    monkeypatch.setattr(base, 'create_engine', lambda url, **kwargs: chamadas.append((url, kwargs)))
    base._criar_engine()
    url, kwargs = chamadas[0]
    assert kwargs['hide_parameters'] and kwargs['pool_pre_ping']
    assert (kwargs['pool_size'], kwargs['max_overflow'], kwargs['pool_timeout']) == (3, 2, 4)
    assert kwargs['connect_args']['connect_timeout'] == 10
    assert 'statement_timeout=15000' in kwargs['connect_args']['options']
    assert 'search_path=pg_catalog,public' in kwargs['connect_args']['options']


def test_identidade_e_titularidade_nao_podem_ser_trocadas_por_update():
    assert 'papel' not in COLUNAS_UPDATE['usuarios']
    assert 'cpf' not in COLUNAS_UPDATE['usuarios']
    assert COLUNAS_UPDATE['carteiras'] == {'saldo', 'saldo_bloqueado'}
