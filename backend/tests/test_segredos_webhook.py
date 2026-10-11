"""Ciphertext no banco, contexto autenticado, legado e rotação sem trocar HMAC."""
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from app.core import segredos_webhook as cofre
from app.core.config import get_settings
from app.repositories import get_repository
from tests.test_outbox_webhooks import loja  # noqa: F401


def test_banco_guarda_ciphertext_e_api_nao_expoe_segredo(cliente, loja):
    dono, numero, _ = loja
    repo = get_repository()
    conta = repo.obter_conta_por_numero(numero)
    w = repo.criar_webhook(empresa_id=conta['empresa_id'], url='https://erp.exemplo.com',
                           segredo='segredo-hmac-teste', eventos=['pix.recebido'])
    with repo._sf() as s:
        bruto = s.scalar(text('SELECT segredo FROM webhooks WHERE id = :id'), {'id': w['id']})
    assert bruto.startswith(cofre.PREFIXO)
    assert 'segredo-hmac-teste' not in bruto
    assert repo.obter_webhook_com_segredo(w['id'])['segredo'] == 'segredo-hmac-teste'
    assert 'segredo' not in w
    assert all('segredo' not in item for item in repo.listar_webhooks(conta['empresa_id']))


def test_contexto_e_adulteracao_sao_recusados():
    valor = cofre.cifrar('segredo-teste', 1)
    with pytest.raises(RuntimeError, match='autenticar'):
        cofre.decifrar(valor, 2)
    with pytest.raises(RuntimeError, match='autenticar'):
        cofre.decifrar(valor[:-10] + 'XXXXXXXXXX', 1)
    with pytest.raises(RuntimeError, match='legado'):
        cofre.decifrar('segredo-antigo', 1)


def test_migracao_legado_rotacao_e_rollback(cliente, loja, monkeypatch):
    from scripts.cifrar_webhooks import migrar
    repo = get_repository()
    with repo._sf() as s:
        [empresa] = s.execute(text('SELECT empresa_id FROM webhooks LIMIT 1')).one()
    w = repo.criar_webhook(empresa_id=empresa, url='https://erp.exemplo.com',
                           segredo='segredo-original', eventos=['pix.recebido'])
    with repo._sf.begin() as s:
        s.execute(text('UPDATE webhooks SET segredo = :v WHERE id = :id'), {'v':'segredo-legado', 'id':w['id']})
    antiga = get_settings().webhook_keys
    with repo._sf.kw['bind'].begin() as c:
        assert migrar(c) >= 2
    assert repo.obter_webhook_com_segredo(w['id'])['segredo'] == 'segredo-legado'
    nova = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), 'webhook_keys', nova + ',' + antiga)
    with repo._sf.kw['bind'].begin() as c:
        migrar(c)
    monkeypatch.setattr(get_settings(), 'webhook_keys', nova)
    assert repo.obter_webhook_com_segredo(w['id'])['segredo'] == 'segredo-legado'
    # Uma chave ausente/ciphertext adulterado faz reverter a migração inteira.
    with repo._sf.begin() as s:
        s.execute(text('UPDATE webhooks SET segredo = :v WHERE id = :id'), {'v':'enc:v1:invalido', 'id':w['id']})
    with repo._sf() as s:
        antes = list(s.execute(text('SELECT id, segredo FROM webhooks ORDER BY id')))
    with pytest.raises(RuntimeError):
        with repo._sf.kw['bind'].begin() as c:
            migrar(c)
    with repo._sf() as s:
        assert list(s.execute(text('SELECT id, segredo FROM webhooks ORDER BY id'))) == antes



def test_chaves_nao_aceitam_alias_ou_reutilizacao_de_material():
    chave = Fernet.generate_key().decode()
    with pytest.raises(RuntimeError, match='WEBHOOK_KEYS'):
        cofre.validar_chaves(chave[:12] + '\n' + chave[12:])
    with pytest.raises(RuntimeError, match='WEBHOOK_KEYS'):
        cofre.validar_chaves(chave, proibidas=[chave[:12] + '\n' + chave[12:]])
    with pytest.raises(RuntimeError, match='WEBHOOK_KEYS'):
        cofre.validar_chaves(chave + ',' + chave)
