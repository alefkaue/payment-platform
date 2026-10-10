"""Boot de produção (SEGURANCA.md item 8): sem segredo forte ou com CORS aberto, nem sobe."""

import pytest

from app.core import config

FERNET = "OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk="


@pytest.fixture
def producao(monkeypatch):
    """Ambiente de produção válido; cada teste estraga uma coisa."""
    valido = {
        "AMBIENTE": "producao",
        "JWT_SECRET": "x" * 48,
        "EMBEDDING_KEY": FERNET,
        "ADMIN_SENHA": "uma-senha-de-admin-forte",
        "CORS_ORIGINS": "https://app.astro.com.br,https://pentest.astro.com.br",
        "CORS_ORIGIN_REGEX": "",
        "BIOMETRIA_STUB": "0",
        "DEPOSITO_DEMO": "0",
        "CNPJ_PROVEDOR": "brasilapi",
        "DOCUMENTO_PROVEDOR": "auto",
        "KYC_DOCUMENTO_OBRIGATORIO": "1",
        "DPOP_OBRIGATORIO": "1",
    }
    for k, v in valido.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


def test_producao_valida_sobe(producao):
    assert config.get_settings().em_producao


@pytest.mark.parametrize(
    ("variavel", "valor", "erro"),
    [
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
