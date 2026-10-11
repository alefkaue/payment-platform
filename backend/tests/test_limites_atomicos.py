"""Orçamento reservado antes do trabalho caro, com disputa entre repositórios."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading

from fastapi import HTTPException
from app.core import tempo
from app.core.limites import limitar_por_ip
from app.repositories import get_repository
from app.repositories.repository import Repositorio


def test_limite_nao_pode_ser_ultrapassado_em_rajada(cliente, monkeypatch):
    repo = get_repository()
    barreira = threading.Barrier(12)
    escrita = threading.Lock()
    contar = repo.contar_eventos
    registrar = repo.registrar_sessao_mfa
    def contar_em_disputa(**kwargs):
        # Faz os leitores antigos observarem o mesmo saldo disponível.
        with escrita:
            quantidade = contar(**kwargs)
        barreira.wait(timeout=10)
        return quantidade
    def registrar_serializado(**kwargs):
        with escrita:
            return registrar(**kwargs)
    monkeypatch.setattr(repo, 'contar_eventos', contar_em_disputa)
    monkeypatch.setattr(repo, 'registrar_sessao_mfa', registrar_serializado)
    def tentar(_):
        try:
            limitar_por_ip(repo, tipo='limite_teste', ip='203.0.113.4', maximo=3,
                           janela_min=1, mensagem='Limite atingido.')
            return True
        except HTTPException as e:
            assert e.status_code == 429
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        resultados = list(pool.map(tentar, range(12)))
    assert sum(resultados) == 3
    assert contar(tipo='limite_teste', desde=tempo.agora()-timedelta(minutes=1),
                  sucesso=None, ip='203.0.113.4') == 3


def test_reserva_compartilhada_e_recuperacao_da_janela(cliente, relogio):
    repo = get_repository()
    outro = Repositorio(repo._sf)
    kwargs = dict(tipo='reserva_teste', maximo=2, janela_min=1, ip='203.0.113.5')
    assert repo.consumir_orcamento(**kwargs)
    assert outro.consumir_orcamento(**kwargs)
    assert not repo.consumir_orcamento(**kwargs)
    assert repo.consumir_orcamento(**{**kwargs, 'ip': '203.0.113.6'})
    relogio.definir(tempo.agora() + timedelta(minutes=1, seconds=1))
    assert outro.consumir_orcamento(**kwargs)


def test_reserva_por_usuario_e_recusa_sem_gravar(cliente):
    repo = get_repository()
    # Sem FK de usuário: usar referência também valida isolamento entre sujeitos.
    assert repo.consumir_orcamento(tipo='reserva_ref', maximo=1, janela_min=1, referencia='a')
    assert not repo.consumir_orcamento(tipo='reserva_ref', maximo=1, janela_min=1, referencia='a')
    assert repo.consumir_orcamento(tipo='reserva_ref', maximo=1, janela_min=1, referencia='b')



def test_postgres_disputa_entre_repositorios(cliente):
    import pytest
    from app.db.base import usando_postgres
    if not usando_postgres():
        pytest.skip('disputa entre conexões exige PostgreSQL')
    original = get_repository()
    barreira = threading.Barrier(8)
    def tentar(_):
        repo = Repositorio(original._sf)
        barreira.wait(timeout=10)
        return repo.consumir_orcamento(tipo='limite_pg', maximo=3, janela_min=1, ip='203.0.113.88')
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(tentar, range(8))) == 3
    assert original.contar_eventos(tipo='limite_pg', desde=tempo.agora()-timedelta(minutes=1),
                                  sucesso=None, ip='203.0.113.88') == 3
