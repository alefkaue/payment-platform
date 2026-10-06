"""
Fixtures de teste. Rodam contra SQLite em memória (sem Postgres, sem Docker) e
com o DeepFace FALSIFICADO (monkeypatch), pra os testes não precisarem de
TensorFlow/opencv nem de uma foto real -- o que testamos aqui é a LÓGICA
(auth, split, saldo, autorização, idempotência), não o modelo de visão.

A biometria real tem seu próprio caminho (services/biometria_service.py) e é
exercitada manualmente / em ambiente com os pesos baixados.
"""

import os

import pytest

# Precisa estar setado ANTES de importar qualquer coisa que leia settings.
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory (StaticPool, ver db/base.py)
os.environ["JWT_SECRET"] = "test-secret-nao-use-em-producao"
os.environ["EMBEDDING_KEY"] = "OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk="  # Fernet válida (teste)
os.environ["ADMIN_SENHA"] = "admin-teste-123"
os.environ["AMBIENTE"] = "desenvolvimento"
os.environ["LIMITE_FACIAL_REAIS"] = "500"


@pytest.fixture()
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    # Falsifica a biometria: cadastro devolve um embedding fixo; verificação
    # devolve "bateu". Assim exercitamos o resto do fluxo sem o modelo real.
    from app.services import biometria_service

    monkeypatch.setattr(biometria_service, "cadastrar_biometria", lambda foto: [0.1, 0.2, 0.3])
    monkeypatch.setattr(
        biometria_service,
        "verificar_biometria",
        lambda foto, emb: {"verificado": True, "distancia": 0.1, "limite": 0.4, "confianca": 99.0, "modelo": "fake"},
    )

    from app.repositories import get_repository

    get_repository.cache_clear()

    # O SQLite in-memory (StaticPool) persiste na conexão única do processo, então
    # dropamos e recriamos o schema a cada teste pra isolar. O startup do app (no
    # enter do TestClient) seeda o split e cria a conta Governo em seguida.
    from app.db import models  # noqa: F401 -- registra os modelos
    from app.db.base import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_repository.cache_clear()


FOTO_FAKE = "data:image/png;base64,Zm9v"  # conteúdo irrelevante (biometria falsificada)
