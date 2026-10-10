"""Transição honesta do split (LC 214/2025): 2026 é ano de teste -- o imposto aparece,
mas não é retido; a retenção começa em SPLIT_RETENCAO_DESDE (padrão 2027-01-01)."""

from datetime import date

import pytest

from app.core import config
from tests.helpers import Pessoa, depositar, gerar_chave_nfe
from tests.test_cobrancas import _cobrar, _empresa


def _venda(cliente):
    dono, n, cnpj = _empresa(cliente)
    pf = Pessoa(cliente, "comprador.transicao@ex.com")
    depositar(cliente, pf.numero, 1000)
    [c] = _cobrar(cliente, dono, n, valor="400.00",
                  nota_fiscal={"chave": gerar_chave_nfe(cnpj), "cbs": "3.60", "ibs": "0.40"})
    return dono, n, pf, c


def test_em_2026_mostra_o_imposto_mas_nao_retem(cliente, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "split_retencao_desde", date(2027, 1, 1))
    dono, n, pf, c = _venda(cliente)
    assert c["split_fase"] == "informativo" and c["vai_reter_imposto"] is False
    t = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h()).json()
    assert (t["liquido"], t["cbs"], t["ibs"]) == ("400.00", "0.00", "0.00")
    assert dono.saldo(n) == "400.00"  # a empresa recebe o valor inteiro
    r = cliente.get("/empresas/atual/tributos", headers=dono.h(n)).json()
    assert (r["split_fase"], r["imposto_destacado"], r["cbs_retido"]) == ("informativo", "4.00", "0.00")
    assert "não é retido" in r["observacao"]


def test_a_partir_de_2027_retem(cliente, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "split_retencao_desde", date(2026, 10, 1))
    dono, n, pf, c = _venda(cliente)
    assert c["split_fase"] == "retencao"
    t = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h()).json()
    assert (t["liquido"], t["cbs"], t["ibs"]) == ("396.00", "3.60", "0.40")


def test_modo_demonstracao_retem_e_se_identifica(cliente, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "split_retencao_desde", date(2027, 1, 1))
    monkeypatch.setattr(config.get_settings(), "split_demonstracao", True)
    dono, n, pf, c = _venda(cliente)
    assert c["split_fase"] == "demonstracao" and c["vai_reter_imposto"] is True
    cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h())
    r = cliente.get("/empresas/atual/tributos", headers=dono.h(n)).json()
    assert r["split_fase"] == "demonstracao" and "Simulação" in r["observacao"]


def test_demonstracao_proibida_em_producao(monkeypatch):
    from tests.test_config_producao import FERNET

    for k, v in {"AMBIENTE": "producao",
                 "DATABASE_URL": "postgresql+psycopg2://a:b@h:5432/x?sslmode=verify-full&sslrootcert=/x.crt",
                 "JWT_SECRET": "x" * 48, "EMBEDDING_KEY": FERNET, "ADMIN_SENHA": "uma-senha-de-admin-forte",
                 "CORS_ORIGINS": "https://app.astro.com.br", "CORS_ORIGIN_REGEX": "", "BIOMETRIA_STUB": "0",
                 "DEPOSITO_DEMO": "0", "CNPJ_PROVEDOR": "brasilapi", "DOCUMENTO_PROVEDOR": "auto",
                 "KYC_DOCUMENTO_OBRIGATORIO": "1", "DPOP_OBRIGATORIO": "1", "SPLIT_DEMONSTRACAO": "1"}.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SPLIT_DEMONSTRACAO"):
            config.get_settings()
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


def test_comprovante_mostra_o_imposto_da_nota_mesmo_sem_reter(cliente, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "split_retencao_desde", date(2027, 1, 1))
    dono, n, pf, c = _venda(cliente)
    t = cliente.post(f"/cobrancas/{c['txid']}/pagar", json={}, headers=pf.h()).json()
    comp = cliente.get(f"/pagamentos/transacoes/{t['id']}", headers=pf.h()).json()
    assert comp["cbs"] == "0.00" and (comp["nota"]["cbs"], comp["nota"]["ibs"]) == ("3.60", "0.40")
