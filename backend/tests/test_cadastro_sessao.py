from app.core.config import get_settings
from app.services import biometria_service
from tests.helpers import SENHA, gerar_cpf, prova_cadastro


def dados(cliente):
    return {'nome': 'Nova Pessoa', 'email': 'nova@ex.com', 'senha': SENHA,
            'cpf': gerar_cpf(), 'biometria': prova_cadastro(cliente)}


def test_uma_prova_e_proximo_login_exige_mfa(cliente, monkeypatch):
    original = biometria_service.cadastrar
    chamadas = []
    def capturar(*args, **kwargs):
        chamadas.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(biometria_service, 'cadastrar', capturar)
    p = dados(cliente)
    r = cliente.post('/usuarios/cadastro-sessao', json=p, headers={'X-Dispositivo-Id': 'aparelho'})
    assert r.status_code == 201, r.text
    assert len(chamadas) == 1
    h = {'Authorization': f"Bearer {r.json()['tokens']['access_token']}", 'X-Dispositivo-Id': 'aparelho'}
    assert cliente.get('/contas', headers=h).status_code == 200
    assert cliente.get('/contas', headers={**h, 'X-Dispositivo-Id': 'outro'}).status_code == 401
    login = cliente.post('/auth/login', json={'email': p['email'], 'senha': SENHA}, headers={'X-Dispositivo-Id': 'aparelho'})
    assert login.status_code == 200
    assert login.json()['mfa_requerido'] is True
    assert login.json()['access_token'] is None
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 409


def test_sem_dpop_nao_cria_conta(cliente, monkeypatch):
    p = dados(cliente)
    monkeypatch.setattr(get_settings(), 'dpop_obrigatorio', True)
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 400
    monkeypatch.setattr(get_settings(), 'dpop_obrigatorio', False)
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 201


def test_atestacao_exigida_antes_de_criar(cliente, monkeypatch):
    p = dados(cliente)
    monkeypatch.setattr(get_settings(), 'atestacao_exigida', True)
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 403
    monkeypatch.setattr(get_settings(), 'atestacao_exigida', False)
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 201


def test_prova_invalida_nao_emite_sessao(cliente):
    p = dados(cliente)
    p['biometria']['desafio_id'] = 'desafio-inexistente'
    r = cliente.post('/usuarios/cadastro-sessao', json=p)
    assert r.status_code == 401
    assert 'tokens' not in r.json()


def test_desafio_login_nao_substitui_cadastro(cliente):
    from tests.helpers import prova
    p = dados(cliente)
    p['biometria'] = prova(cliente, modo='login')
    assert cliente.post('/usuarios/cadastro-sessao', json=p).status_code == 400
