"""Boot de produção (SEGURANCA.md item 8): sem segredo forte ou com CORS aberto, nem sobe."""

import pytest

from app.core import config

FERNET = "OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk="


@pytest.fixture
def producao(monkeypatch):
    """Ambiente de produção válido; cada teste estraga uma coisa."""
    valido = {
        "AMBIENTE": "producao",
        "DEMONSTRACAO_PUBLICA": "0",
        "DATABASE_URL": "postgresql+psycopg2://astro_app:teste@banco:5432/astro?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt",
        "JWT_SECRET": "x" * 48,
        "EMBEDDING_KEY": FERNET,
        "WEBHOOK_KEYS": "d2ViaG9vay10ZXN0ZS1jaGF2ZS0zMi1ieXRlcyEhISE=",
        "PII_KEYS": "Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8=",
        "PII_INDEX_KEY": "ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA=",
        "DATABASE_CONTEXT_KEY": "ISEhISEhISEhISEhISEhISEhISEhISEhISEhISEhISE=",
        "ADMIN_SENHA": "uma-senha-de-admin-forte",
        "CORS_ORIGINS": "https://app.astro.com.br,https://pentest.astro.com.br",
        "CORS_ORIGIN_REGEX": "",
        "BIOMETRIA_STUB": "0",
        "DEPOSITO_DEMO": "0",
        "CNPJ_PROVEDOR": "brasilapi",
        "DOCUMENTO_PROVEDOR": "auto",
        "KYC_DOCUMENTO_OBRIGATORIO": "1",
        "DPOP_OBRIGATORIO": "1",
        "BENEFICIOS_HABILITADOS": "0",
        "DPOP_ORIGEM_PUBLICA": "https://api.astro.test",
    }
    for k, v in valido.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


def test_producao_valida_sobe(producao):
    assert config.get_settings().em_producao


def test_admin_ligado_em_producao_exige_totp(producao):
    producao.setenv("ADMIN_IPS_PERMITIDOS", "10.0.0.5")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ADMIN_TOTP_SEGREDO"):
        config.get_settings()
    producao.setenv("ADMIN_TOTP_SEGREDO", "CURTO234")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ADMIN_TOTP_SEGREDO"):
        config.get_settings()
    producao.setenv("ADMIN_TOTP_SEGREDO", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    config.get_settings.cache_clear()
    assert config.get_settings().admin_totp_segredo


@pytest.mark.parametrize(
    ("variavel", "valor", "erro"),
    [
        ("DOCUMENTO_VERIFICAR_IDENTIDADE", "0", "DOCUMENTO_VERIFICAR_IDENTIDADE"),
        ("DATABASE_URL", "", "DATABASE_URL"),
        ("DATABASE_URL", "sqlite://", "PostgreSQL"),
        ("DATABASE_URL", "postgresql://u:p@db/test?sslmode=require", "verify-full"),
        ("JWT_ALGORITMO", "none", "JWT_ALGORITMO"),
        ("JWT_SECRET", "", "JWT_SECRET"),
        ("JWT_SECRET", "curto-demais", "JWT_SECRET"),
        ("EMBEDDING_KEY", "", "EMBEDDING_KEY"),
        ("EMBEDDING_KEY", "nao-e-fernet", "EMBEDDING_KEY"),
        ("ADMIN_SENHA", "", "ADMIN_SENHA"),
        ("ADMIN_SENHA", "curta", "ADMIN_SENHA"),
        ("CORS_ORIGIN_REGEX", r"https://.*\.netlify\.app", "CORS_ORIGIN_REGEX"),
        ("CORS_ORIGINS", "*", "CORS_ORIGINS"),
        ("CORS_ORIGINS", "https://app.astro.com.br,http://app.astro.com.br", "CORS_ORIGINS"),
    ],
)
def test_producao_nao_sobe_mal_configurada(producao, variavel, valor, erro):
    producao.setenv(variavel, valor)
    with pytest.raises(RuntimeError, match=erro):
        config.get_settings()


def test_desenvolvimento_continua_flexivel(producao):
    producao.setenv("AMBIENTE", "desenvolvimento")
    producao.setenv("JWT_SECRET", "")
    producao.setenv("CORS_ORIGINS", "http://localhost:8081")
    assert not config.get_settings().em_producao


def test_beneficios_nao_podem_ser_ligados_em_producao(producao):
    producao.setenv("BENEFICIOS_HABILITADOS", "1")
    with pytest.raises(RuntimeError, match="BENEFICIOS_HABILITADOS"):
        config.get_settings()


def test_beneficios_permanecem_disponiveis_em_desenvolvimento(producao):
    producao.setenv("AMBIENTE", "desenvolvimento")
    producao.setenv("BENEFICIOS_HABILITADOS", "1")
    assert config.get_settings().beneficios_habilitados


@pytest.mark.parametrize('chaves', ['', 'invalida', FERNET])
def test_producao_exige_chave_webhook_separada(producao, chaves):
    producao.setenv('WEBHOOK_KEYS', chaves)
    with pytest.raises(RuntimeError, match='WEBHOOK_KEYS'):
        config.get_settings()



def test_demo_publica_so_flexibiliza_fluxos_simulados(producao):
    producao.setenv('DEMONSTRACAO_PUBLICA', '1')
    producao.setenv('DEPOSITO_DEMO', '1')
    producao.setenv('DOCUMENTO_PROVEDOR', 'stub')
    producao.setenv('KYC_DOCUMENTO_OBRIGATORIO', '0')
    s = config.get_settings()
    assert s.em_producao and s.demonstracao_publica and s.deposito_demo


@pytest.mark.parametrize('variavel,valor,erro', [
    ('DPOP_OBRIGATORIO', '0', 'DPOP_OBRIGATORIO'),
    ('BIOMETRIA_STUB', '1', 'BIOMETRIA_STUB'),
    ('JWT_SECRET', '', 'JWT_SECRET'),
    ('WEBHOOK_KEYS', '', 'WEBHOOK_KEYS'),
    ('DATABASE_URL', 'sqlite://', 'PostgreSQL'),
    ('CORS_ORIGINS', '*', 'CORS_ORIGINS'),
    ('BENEFICIOS_HABILITADOS', '1', 'BENEFICIOS_HABILITADOS'),
])
def test_demo_publica_mantem_controles_producao(producao, variavel, valor, erro):
    producao.setenv('DEMONSTRACAO_PUBLICA', '1')
    producao.setenv(variavel, valor)
    with pytest.raises(RuntimeError, match=erro):
        config.get_settings()


def test_api_deixa_simulacao_explicita(cliente):
    r = cliente.get('/')
    assert r.status_code == 200
    assert r.json()['modo'] == 'simulacao'
    assert r.json()['dinheiro_real'] is False
    assert r.json()['autenticidade_documental'] is False


@pytest.mark.parametrize('variavel', ['PII_KEYS','PII_INDEX_KEY','DATABASE_CONTEXT_KEY'])
def test_chaves_de_dados_obrigatorias(producao,variavel):
    producao.setenv(variavel,'')
    with pytest.raises(RuntimeError,match='PII_KEYS|DATABASE_CONTEXT_KEY'):
        config.get_settings()


@pytest.mark.parametrize('variavel', ['PII_KEYS','PII_INDEX_KEY','DATABASE_CONTEXT_KEY'])
def test_chaves_de_dados_nao_reutilizam_biometria(producao,variavel):
    producao.setenv(variavel,FERNET)
    with pytest.raises(RuntimeError): config.get_settings()


def test_contexto_nao_aceita_multiplas_chaves(producao):
    import base64
    outra=base64.urlsafe_b64encode(bytes([49])*32).decode()
    producao.setenv('DATABASE_CONTEXT_KEY',config.get_settings().database_context_key+','+outra)
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError,match='DATABASE_CONTEXT_KEY'):config.get_settings()
