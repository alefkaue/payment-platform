"""Falhas e trabalho em andamento compartilham o limite entre repositórios."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import pytest
from fastapi import HTTPException
from sqlalchemy import event
from app.core import tempo
from app.repositories import get_repository
from app.repositories.repository import Repositorio
from app.db.models import SessaoMfa

@pytest.mark.parametrize('tipo', ['login', 'biometria'])
def test_reserva_concorrente_nao_ultrapassa_orcamento(cliente, tipo):
    original = get_repository()
    barreira = threading.Barrier(12)
    def tentar(_):
        repo = Repositorio(original._sf)
        barreira.wait(timeout=10)
        return repo.reservar_verificacao(tipo=tipo, janela_min=15,
            limites=[(3, {'referencia': 'teste'})], referencia='teste')
    with ThreadPoolExecutor(max_workers=12) as pool:
        resultados = list(pool.map(tentar, range(12)))
    assert sum(r is not None for r in resultados) == 3


def test_sucesso_libera_falha_persiste_e_conclusao_idempotente(cliente):
    repo = get_repository()
    kwargs = dict(tipo='login', janela_min=15, limites=[(1, {'referencia': 'teste'})], referencia='teste')
    primeira = repo.reservar_verificacao(**kwargs)
    assert primeira is not None
    assert repo.reservar_verificacao(**kwargs) is None
    repo.concluir_verificacao(primeira, sucesso=True)
    segunda = repo.reservar_verificacao(**kwargs)
    assert segunda is not None
    repo.concluir_verificacao(segunda, sucesso=False)
    repo.concluir_verificacao(segunda, sucesso=True)
    assert repo.reservar_verificacao(**kwargs) is None
    assert repo.contar_eventos(tipo='login', desde=tempo.agora()-timedelta(minutes=15), referencia='teste') == 1


def test_reserva_abandonada_expira_sem_apagar_trilha(cliente, relogio):
    repo = get_repository()
    kwargs = dict(tipo='login', janela_min=1, limites=[(1, {'ip': '203.0.113.7'})], ip='203.0.113.7')
    assert repo.reservar_verificacao(**kwargs) is not None
    assert repo.reservar_verificacao(**kwargs) is None
    relogio.definir(tempo.agora()+timedelta(minutes=1, seconds=1))
    assert repo.reservar_verificacao(**kwargs) is not None


def test_limites_conjuntos_nao_consumem_reserva_quando_um_recusa(cliente):
    repo = get_repository()
    assert repo.reservar_verificacao(tipo='login', janela_min=15,
        limites=[(1, {'ip': '203.0.113.8'})], ip='203.0.113.8', referencia='a') is not None
    assert repo.reservar_verificacao(tipo='login', janela_min=15,
        limites=[(10, {'referencia': 'b'}), (1, {'ip': '203.0.113.8'})],
        referencia='b', ip='203.0.113.8') is None
    assert repo.reservar_verificacao(tipo='login', janela_min=15,
        limites=[(1, {'referencia': 'b'})], referencia='b') is not None


def test_falha_ao_concluir_nao_libera_reserva(cliente):
    repo = get_repository()
    kwargs = dict(tipo='login', janela_min=15, limites=[(1, {'referencia': 'teste'})], referencia='teste')
    reserva = repo.reservar_verificacao(**kwargs)
    classe = repo._sf.class_
    def impedir(sessao, *_):
        if any(isinstance(x, SessaoMfa) and x.tipo == 'login_concluido' for x in sessao.new):
            raise RuntimeError('falha de persistência simulada')
    event.listen(classe, 'before_flush', impedir)
    try:
        with pytest.raises(RuntimeError):
            repo.concluir_verificacao(reserva, sucesso=False)
    finally:
        event.remove(classe, 'before_flush', impedir)
    assert repo.reservar_verificacao(**kwargs) is None
    assert repo.contar_eventos(tipo='login', desde=tempo.agora()-timedelta(minutes=15)) == 0
    repo.concluir_verificacao(reserva, sucesso=False)


def test_login_reserva_antes_do_hash_e_nao_trava_sucessos(cliente, monkeypatch):
    from app.core.config import get_settings
    from app.services import auth_service
    repo = get_repository()
    usuario = {'email': 'p@ex.com', 'id': None, 'ativo': True, 'senha_hash': 'teste'}
    monkeypatch.setattr(repo, 'obter_usuario_por_login', lambda _: usuario)
    monkeypatch.setattr(repo, 'registrar_log', lambda **_: None)
    monkeypatch.setattr(get_settings(), 'login_max_tentativas', 3)
    monkeypatch.setattr(auth_service.security, 'precisa_rehash', lambda _: False)
    chegou = threading.Barrier(4)
    liberar = threading.Event()
    def hash_lento(*_):
        chegou.wait(timeout=10)
        assert liberar.wait(timeout=10)
        return False
    monkeypatch.setattr(auth_service.security, 'verificar_senha', hash_lento)
    def tentar():
        try:
            auth_service.autenticar(repo, email='p@ex.com', senha='teste', ip='203.0.113.2')
        except HTTPException as e:
            return e.status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        tarefas = [pool.submit(tentar) for _ in range(3)]
        try:
            chegou.wait(timeout=10)
            assert tentar() == 429
        finally:
            liberar.set()
        assert [t.result() for t in tarefas] == [401]*3
    assert tentar() == 429
    monkeypatch.setattr(auth_service.security, 'verificar_senha', lambda *_: True)
    for _ in range(8):
        assert auth_service.autenticar(repo, email='outro@ex.com', senha='teste', ip='203.0.113.3') == usuario


def test_rosto_reserva_antes_de_iniciar_motor(cliente, monkeypatch):
    from app.core.config import get_settings
    from app.services import seguranca_service
    from tests.helpers import Pessoa
    p = Pessoa(cliente, 'rosto@ex.com')
    repo = get_repository()
    usuario = repo.obter_usuario_por_login(p.email)
    monkeypatch.setattr(get_settings(), 'biometria_max_tentativas', 1)
    def motor(*_, **__):
        assert repo.reservar_verificacao(tipo='biometria', janela_min=15,
            limites=[(1, {'usuario_id': usuario['id']})], usuario_id=usuario['id']) is None
        raise HTTPException(status_code=401, detail='Prova inválida.')
    monkeypatch.setattr(seguranca_service.biometria_service, 'verificar', motor)
    with pytest.raises(HTTPException) as exc:
        seguranca_service.verificar_rosto(repo, usuario=usuario, prova=object(), ip=None, tipo='teste')
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        seguranca_service.verificar_rosto(repo, usuario=usuario, prova=object(), ip=None, tipo='teste')
    assert exc.value.status_code == 429


@pytest.mark.parametrize('status', [400, 503])
def test_erro_de_servico_nao_vira_falso_sucesso_facial(cliente, monkeypatch, status):
    from app.services import seguranca_service
    from tests.helpers import Pessoa
    p = Pessoa(cliente, 'ocupado@ex.com')
    repo = get_repository()
    usuario = repo.obter_usuario_por_login(p.email)
    antes = repo.contar_eventos(tipo='biometria', sucesso=None, desde=tempo.agora()-timedelta(minutes=15),
                               usuario_id=usuario['id'])
    def motor(*_, **__):
        raise HTTPException(status_code=status, detail='Não foi possível processar.')
    monkeypatch.setattr(seguranca_service.biometria_service, 'verificar', motor)
    with pytest.raises(HTTPException) as exc:
        seguranca_service.verificar_rosto(repo, usuario=usuario, prova=object(), ip=None, tipo='teste')
    assert exc.value.status_code == status
    assert repo.contar_eventos(tipo='biometria', sucesso=None, desde=tempo.agora()-timedelta(minutes=15),
                              usuario_id=usuario['id']) == antes
    assert repo.reservar_verificacao(tipo='biometria', janela_min=15,
        limites=[(1, {'usuario_id': usuario['id']})], usuario_id=usuario['id']) is not None
