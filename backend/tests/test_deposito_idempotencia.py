"""Depósito fictício não duplica saldo em reenvios após falha de rede."""
from sqlalchemy import select, func
from app.core.config import get_settings
from app.db.base import SessionLocal
from app.db.models import Transacao, HistoricoSaldo
from tests.helpers import Pessoa


def test_deposito_reenvio_mesmo_valor_e_conflito(cliente, monkeypatch):
    monkeypatch.setattr(get_settings(), 'deposito_demo', True)
    pessoa = Pessoa(cliente, 'deposito.retry@ex.com')
    corpo = {'valor':'12.34', 'idempotency_key':'deposito-unico'}
    primeiro = cliente.post('/pagamentos/depositar-demo', headers=pessoa.h(), json=corpo)
    assert primeiro.status_code == 200, primeiro.text
    segundo = cliente.post('/pagamentos/depositar-demo', headers=pessoa.h(), json=corpo)
    assert segundo.status_code == 200 and segundo.json()['id'] == primeiro.json()['id']
    assert pessoa.saldo() == '12.34'
    conflito = cliente.post('/pagamentos/depositar-demo', headers=pessoa.h(), json={**corpo, 'valor':'20.00'})
    assert conflito.status_code == 409
    assert pessoa.saldo() == '12.34'
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Transacao.id))) == 1
        assert s.scalar(select(func.count(HistoricoSaldo.id))) == 2


def test_deposito_mesma_chave_em_contas_distintas(cliente, monkeypatch):
    monkeypatch.setattr(get_settings(), 'deposito_demo', True)
    a, b = Pessoa(cliente, 'deposito.a@ex.com'), Pessoa(cliente, 'deposito.b@ex.com')
    corpo = {'valor':'5.00', 'idempotency_key':'compartilhada'}
    for p in (a,b):
        assert cliente.post('/pagamentos/depositar-demo', headers=p.h(), json=corpo).status_code == 200
        assert p.saldo() == '5.00'


def test_deposito_header_confere_com_corpo(cliente, monkeypatch):
    monkeypatch.setattr(get_settings(), 'deposito_demo', True)
    p = Pessoa(cliente, 'deposito.header@ex.com')
    h = {**p.h(), 'Idempotency-Key':'cabecalho'}
    assert cliente.post('/pagamentos/depositar-demo', headers=h, json={'valor':'1.00','idempotency_key':'outro'}).status_code == 400
    assert p.saldo() == '0.00'
    for _ in range(2):
        assert cliente.post('/pagamentos/depositar-demo', headers=h, json={'valor':'1.00'}).status_code == 200
    assert p.saldo() == '1.00'
