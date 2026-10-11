"""Timeout real e ausência de credenciais no processo de análise."""
import sys
import time
import pytest
from fastapi import HTTPException
from app.core import arquivos
from tests.test_pentest_20261010 import _pdf_sintetico


def test_pdf_valido_e_ativo_em_processo_isolado():
    arquivos._validar_pdf(_pdf_sintetico())
    with pytest.raises(HTTPException) as erro:
        arquivos._validar_pdf(_pdf_sintetico(ativo=True))
    assert erro.value.status_code == 415


def test_worker_lento_e_encerrado_por_timeout(monkeypatch):
    monkeypatch.setattr(arquivos, '_COMANDO_PDF', (sys.executable, '-c', 'import time; time.sleep(5)'))
    monkeypatch.setattr(arquivos, '_TEMPO_PDF', 0.1)
    inicio = time.monotonic()
    with pytest.raises(HTTPException) as erro:
        arquivos._validar_pdf(b'pdf-teste')
    assert erro.value.status_code == 413
    assert time.monotonic() - inicio < 2


def test_worker_nao_recebe_segredos_do_pai(monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'segredo-que-nao-deve-chegar-ao-worker')
    monkeypatch.setenv('DATABASE_URL', 'banco-privado')
    codigo = "import os,sys; sys.stdout.write('ok' if not any(k in os.environ for k in ('JWT_SECRET','DATABASE_URL','WEBHOOK_KEYS')) else 'vazou')"
    monkeypatch.setattr(arquivos, '_COMANDO_PDF', (sys.executable, '-c', codigo))
    arquivos._validar_pdf(b'pdf-teste')


def test_worker_linux_aplica_quotas_reais():
    import subprocess
    if sys.platform != 'linux':
        pytest.skip('quotas POSIX verificadas em Linux')
    codigo = "from app.core.pdf_worker import aplicar_limites; aplicar_limites(); import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0]); print(resource.getrlimit(resource.RLIMIT_CPU)[1]); print(resource.getrlimit(resource.RLIMIT_CORE)[0])"
    r = subprocess.run([sys.executable, '-c', codigo], capture_output=True, check=True, timeout=5)
    assert r.stdout.splitlines() == [str(384*1024*1024).encode(), b'3', b'0']



def test_extracao_usa_worker_e_recusa_pdf_ativo():
    from app.services.documento_service import _texto_pdf
    assert isinstance(_texto_pdf(_pdf_sintetico()), str)
    with pytest.raises(HTTPException) as erro:
        _texto_pdf(_pdf_sintetico(ativo=True))
    assert erro.value.status_code == 415



def test_worker_tem_admissao_limitada_e_devolve_vagas():
    assert arquivos._VAGAS_PDF.acquire(blocking=False)
    assert arquivos._VAGAS_PDF.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as erro:
            arquivos._validar_pdf(_pdf_sintetico())
        assert erro.value.status_code == 503
    finally:
        arquivos._VAGAS_PDF.release()
        arquivos._VAGAS_PDF.release()
    arquivos._validar_pdf(_pdf_sintetico())
