from types import SimpleNamespace
import pytest
from sqlalchemy import func, select
from app.core.documentos import normalizar_celular
from app.db.base import SessionLocal
from app.db.models import Usuario
from app.services import biometria_service, face_engine
from tests.helpers import Pessoa, SENHA, gerar_cpf, prova_cadastro

@pytest.mark.parametrize('valor', ['1134567890', '1198765432', '119876543210', '20987654321', '11887654321', 'abc11987654321', '+1 11987654321'])
def test_celular_invalido_recusado_pela_api(cliente, valor):
    r = cliente.post('/usuarios', json={'nome': 'Cadastro Teste', 'email': 'cel@ex.com', 'cpf': gerar_cpf(), 'senha': SENHA, 'celular': valor, 'biometria': prova_cadastro(cliente)})
    assert r.status_code == 422
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Usuario.id)).where(Usuario.email == 'cel@ex.com')) == 0

@pytest.mark.parametrize('valor', ['11987654321', '(11) 98765-4321', '+55 (11) 98765-4321'])
def test_celular_normalizado(valor):
    assert normalizar_celular(valor) == '+5511987654321'

def _cadastrar(cliente, email, cpf=None):
    return cliente.post('/usuarios', json={'nome': 'Cadastro Teste', 'email': email, 'cpf': cpf or gerar_cpf(), 'senha': SENHA, 'celular': '(11) 98765-4321', 'biometria': prova_cadastro(cliente)})

def test_cpf_duplicado_com_formatacao_recusado(cliente):
    a = Pessoa(cliente, 'original@ex.com')
    cpf = f'{a.cpf[:3]}.{a.cpf[3:6]}.{a.cpf[6:9]}-{a.cpf[9:]}'
    assert _cadastrar(cliente, 'outro@ex.com', cpf).status_code == 409
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Usuario.id)).where(Usuario.cpf == a.cpf)) == 1

def _motor(monkeypatch):
    monkeypatch.setattr(face_engine, 'motor', lambda: SimpleNamespace(nome='sface', limiar=.42, similaridade=face_engine._cosseno))

def test_mesmo_rosto_com_outro_documento_recusado(cliente, monkeypatch):
    _motor(monkeypatch)
    vetores = iter([[1., 0., 0.], [.99, .01, 0.]])
    monkeypatch.setattr(biometria_service, 'cadastrar', lambda *a, **k: {'modelo': 'sface', 'vetor': next(vetores)})
    assert _cadastrar(cliente, 'primeiro@ex.com').status_code == 201
    r = _cadastrar(cliente, 'segundo@ex.com')
    assert r.status_code == 409
    assert 'rosto' not in r.json()['detail'].lower()
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Usuario.id)).where(Usuario.email.in_(['primeiro@ex.com','segundo@ex.com']))) == 1

def test_rostos_diferentes_podem_cadastrar(cliente, monkeypatch):
    _motor(monkeypatch)
    vetores = iter([[1., 0., 0.], [0., 1., 0.]])
    monkeypatch.setattr(biometria_service, 'cadastrar', lambda *a, **k: {'modelo': 'sface', 'vetor': next(vetores)})
    assert _cadastrar(cliente, 'primeiro@ex.com').status_code == 201
    assert _cadastrar(cliente, 'segundo@ex.com').status_code == 201

def test_template_corrompido_nao_libera_novo_cadastro(cliente, monkeypatch):
    a = Pessoa(cliente, 'antigo@ex.com')
    with SessionLocal() as s:
        u = s.scalar(select(Usuario).where(Usuario.email == a.email))
        u.embedding_facial_cifrado = b'corrompido'
        s.commit()
    _motor(monkeypatch)
    monkeypatch.setattr(biometria_service, 'cadastrar', lambda *a, **k: {'modelo': 'sface', 'vetor': [1., 0., 0.]})
    assert _cadastrar(cliente, 'novo@ex.com').status_code == 503


def test_cadastro_real_nao_aceita_quadros_falsos_mesmo_com_login_demo(cliente, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'biometria_stub_cadastro', False)
    # A análise real é chamada, e recebe/rejeita os quadros de teste.
    from fastapi import HTTPException
    def rejeitar(*a, **k):
        raise HTTPException(status_code=400, detail='Imagem inválida')
    monkeypatch.setattr(biometria_service, '_executar', rejeitar)
    assert _cadastrar(cliente, 'nao-falso@ex.com').status_code == 400


def _criar_em_processo(dados, barreira, fila):
    from app.db.base import engine
    from app.repositories import get_repository
    from app.repositories.exceptions import RostoDuplicadoError
    engine.dispose(close=False)
    barreira.wait(timeout=15)
    try:
        get_repository().criar_pessoa(**dados)
        fila.put('criado')
    except RostoDuplicadoError:
        fila.put('duplicado')
    except Exception as e:
        fila.put(type(e).__name__)


def test_cadastro_mesmo_rosto_em_processos_distintos(cliente, monkeypatch):
    import os
    import multiprocessing
    from app.core import security
    if not os.environ.get('TEST_DATABASE_URL', '').startswith('postgresql'):
        pytest.skip('requer PostgreSQL e processos independentes')
    _motor(monkeypatch)
    contexto = multiprocessing.get_context('fork')
    barreira, fila = contexto.Barrier(2), contexto.Queue()
    ps = []
    for i in range(2):
        dados = {'nome': 'Cadastro Paralelo', 'email': f'paralelo{i}@ex.com', 'cpf': gerar_cpf(),
                 'senha_hash': security.hash_senha(SENHA),
                 'embedding_cifrado': security.cifrar_embedding([1., 0., 0.], 'sface')}
        p = contexto.Process(target=_criar_em_processo, args=(dados, barreira, fila))
        p.start()
        ps.append(p)
    try:
        respostas = [fila.get(timeout=25) for _ in ps]
        assert sorted(respostas) == ['criado', 'duplicado']
    finally:
        for p in ps:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
                p.join()


def test_cpf_unicode_nao_contorna_duplicidade(cliente):
    a = Pessoa(cliente, 'original-unicode@ex.com')
    cpf = ''.join(chr(ord('０') + int(d)) for d in a.cpf[:9]) + a.cpf[9:]
    assert _cadastrar(cliente, 'duplicado-unicode@ex.com', cpf).status_code == 400


@pytest.mark.parametrize('campo,valor', [('cpf','５2998224725'), ('cpf','529.982.247-25'), ('celular','+551134567890'), ('celular','+5520987654321')])
def test_banco_recusa_documento_ou_celular_fora_do_formato(cliente, campo, valor):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, DataError
    a = Pessoa(cliente, 'canonico@ex.com')
    with SessionLocal() as s, pytest.raises((IntegrityError, DataError)):
        s.execute(text(f'UPDATE usuarios SET {campo} = :valor WHERE email = :email'), {'valor':valor, 'email':a.email})
        s.commit()
