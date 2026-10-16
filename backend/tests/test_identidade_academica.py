"""Modo acadêmico: conta nova opera na hora (identidade simulada), mas usuário
inativo/suspenso continua bloqueado e produção real segue exigindo KYC aprovado.
Testa o portão Repositorio._exigir_identidade_financeira (ativação imediata, #3)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.repositories.repository as repo_mod
from app.db.models import TipoPessoa
from app.repositories.repository import Repositorio


def _cfg(**kw):
    base = dict(em_producao=True, demonstracao_publica=True, documento_verificar_identidade=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _sessao(usuario=None, empresa=None):
    s = MagicMock()

    def get(model, _id):
        return {"Usuario": usuario, "Empresa": empresa}.get(model.__name__)

    s.get.side_effect = get
    return s


def _carteira_pf(uid=1):
    return SimpleNamespace(titular_tipo=TipoPessoa.PF, usuario_id=uid, empresa_id=None)


def _carteira_pj(eid=1):
    return SimpleNamespace(titular_tipo=TipoPessoa.PJ, usuario_id=None, empresa_id=eid)


def test_academico_conta_pf_pendente_opera_na_hora(monkeypatch):
    monkeypatch.setattr(repo_mod, "get_settings", lambda: _cfg())
    s = _sessao(usuario=SimpleNamespace(ativo=True, kyc_status="pendente"))
    # Não levanta: no modo acadêmico a identidade é simulada, a conta opera.
    Repositorio._exigir_identidade_financeira(s, _carteira_pf())


def test_academico_usuario_inativo_continua_bloqueado(monkeypatch):
    monkeypatch.setattr(repo_mod, "get_settings", lambda: _cfg())
    s = _sessao(usuario=SimpleNamespace(ativo=False, kyc_status="pendente"))
    with pytest.raises(ValueError):
        Repositorio._exigir_identidade_financeira(s, _carteira_pf())


def test_academico_titular_inexistente_bloqueado(monkeypatch):
    monkeypatch.setattr(repo_mod, "get_settings", lambda: _cfg())
    s = _sessao(usuario=None)
    with pytest.raises(ValueError):
        Repositorio._exigir_identidade_financeira(s, _carteira_pf())


def test_producao_real_sem_academico_exige_kyc_aprovado(monkeypatch):
    monkeypatch.setattr(
        repo_mod, "get_settings",
        lambda: _cfg(demonstracao_publica=False, documento_verificar_identidade=True))
    s = _sessao(usuario=SimpleNamespace(ativo=True, kyc_status="pendente"))
    with pytest.raises(ValueError):
        Repositorio._exigir_identidade_financeira(s, _carteira_pf())


def test_academico_pj_opera_mas_representante_inativo_bloqueia(monkeypatch):
    monkeypatch.setattr(repo_mod, "get_settings", lambda: _cfg())
    emp = SimpleNamespace(kyb_status="pendente", representante_usuario_id=7)
    # representante ativo -> opera
    s_ok = _sessao(usuario=SimpleNamespace(ativo=True, kyc_status="pendente"), empresa=emp)
    Repositorio._exigir_identidade_financeira(s_ok, _carteira_pj())
    # representante inativo -> bloqueia mesmo no acadêmico
    s_bad = _sessao(usuario=SimpleNamespace(ativo=False, kyc_status="pendente"), empresa=emp)
    with pytest.raises(ValueError):
        Repositorio._exigir_identidade_financeira(s_bad, _carteira_pj())
