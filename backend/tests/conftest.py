"""
Fixtures de teste. Rodam contra SQLite em memória (sem Postgres, sem Docker) e
com BIOMETRIA_STUB ligado: o DeepFace não é chamado, mas o DESAFIO de biometria
continua sendo conferido (existe, não expirou, uso único, dono certo). O que se
testa aqui é a lógica (dinheiro, split, limites, permissões), não o modelo de visão.
"""

import os

import pytest

# Precisa estar setado ANTES de importar qualquer coisa que leia settings.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-nao-use-em-producao"
os.environ["EMBEDDING_KEY"] = "OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk="
os.environ["ADMIN_SENHA"] = "admin-teste-123"
os.environ["AMBIENTE"] = "desenvolvimento"
os.environ["LIMITE_FACIAL_REAIS"] = "500"
os.environ["BIOMETRIA_STUB"] = "1"
os.environ["WEBHOOK_ENTREGA_IMEDIATA"] = "0"
os.environ["CNPJ_PROVEDOR"] = "stub"
os.environ["SPLIT_VIGENCIA"] = "2026"


@pytest.fixture()
def cliente(monkeypatch):
    from datetime import datetime, timezone

    from fastapi.testclient import TestClient

    from app.core import tempo
    from app.repositories import get_repository

    # Relógio fixo em horário DIURNO (quarta, 12h em Brasília): sem isso, os
    # testes mudam de resultado quando rodam à noite (limite noturno). Quem
    # precisa de outro horário usa a fixture `relogio`.
    monkeypatch.setattr(tempo, "agora", lambda: datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))

    get_repository.cache_clear()
    from app.db import models  # noqa: F401
    from app.db.base import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from app.main import app

    with TestClient(app) as c:
        yield c
    get_repository.cache_clear()


@pytest.fixture()
def relogio(monkeypatch):
    """Controla o 'agora' da aplicação: relogio.definir(datetime_utc)."""
    from app.core import tempo

    class Relogio:
        def definir(self, momento):
            monkeypatch.setattr(tempo, "agora", lambda: momento)

    return Relogio()
