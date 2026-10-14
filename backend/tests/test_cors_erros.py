"""Erros internos precisam ser legíveis só pelas origens autorizadas."""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("origem,permitida", [
    ("https://frontend.astro.test", True),
    ("https://frontend.astro.test.evil.example", False),
    ("https://evil.example", False),
])
def test_erro_interno_preserva_cors_sem_vazar_excecao(cliente, monkeypatch, origem, permitida):
    from app.main import app, settings
    from app.services import biometria_service

    monkeypatch.setattr(settings, "cors_origins", "https://frontend.astro.test")
    monkeypatch.setattr(settings, "cors_origin_regex", None)

    def falhar(*args, **kwargs):
        raise RuntimeError("segredo-interno-nao-publicar")

    monkeypatch.setattr(biometria_service, "criar_desafio", falhar)
    with TestClient(app, raise_server_exceptions=False) as browser:
        resposta = browser.post("/biometria/desafios", json={"modo": "cadastro"},
                                headers={"Origin": origem})

    assert resposta.status_code == 500
    assert "segredo-interno-nao-publicar" not in resposta.text
    assert resposta.json()["request_id"] == resposta.headers["X-Request-Id"]
    assert resposta.headers["Cache-Control"] == "no-store"
    if permitida:
        assert resposta.headers["Access-Control-Allow-Origin"] == origem
        assert resposta.headers["Vary"] == "Origin"
    else:
        assert "Access-Control-Allow-Origin" not in resposta.headers
