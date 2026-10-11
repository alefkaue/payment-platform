"""Regressões do perímetro sem tocar dados de clientes ou serviços externos."""
import asyncio
import logging
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from app.core.perimetro import PerimetroHTTP, ISCAS

async def eco(request):
    return JSONResponse({'bytes': len(await request.body())})

def criar(**kwargs):
    return PerimetroHTTP(Starlette(routes=[Route('/eco', eco, methods=['GET', 'POST']),
                                         Route('/pronto', eco)]), limite=20, **kwargs)

@pytest.mark.parametrize('caminho', sorted(ISCAS))
def test_isca_neutra_sem_eco_e_sem_dados(caminho, caplog):
    with TestClient(criar()) as c, caplog.at_level(logging.INFO, logger='astro.auditoria'):
        resp = c.post(caminho + '?senha=segredo-cliente', json={'senha': 'segredo-cliente'},
                      headers={'Authorization': 'Bearer segredo-token'})
    assert resp.status_code == 404
    assert resp.headers['cache-control'] == 'no-store'
    assert resp.headers['x-content-type-options'] == 'nosniff'
    assert 'segredo' not in resp.text + caplog.text
    evento = next(r for r in caplog.records if r.getMessage() == 'sondagem_rota_isca')
    assert evento.isca == caminho
    assert len(evento.origem) == 24
    assert 'testclient' not in caplog.text

def test_isca_nao_trava_cliente_e_log_tem_teto(caplog):
    with TestClient(criar()) as c, caplog.at_level(logging.INFO, logger='astro.auditoria'):
        assert c.get('/eco').status_code == 200
        for _ in range(10):
            assert c.get('/.env').status_code == 404
        assert c.get('/eco').status_code == 200
    assert len([r for r in caplog.records if r.getMessage() == 'sondagem_rota_isca']) == 1

def test_limite_requisicoes_nao_confia_xff_e_recupera():
    agora = [0.0]
    with TestClient(criar(requisicoes_minuto=2, relogio=lambda: agora[0]), client=('127.0.0.1', 123)) as c:
        assert c.get('/eco').status_code == 200
        assert c.get('/eco').status_code == 200
        resp = c.get('/eco', headers={'X-Forwarded-For': '8.8.8.8'})
        assert resp.status_code == 429
        assert resp.headers['retry-after'] == '1'
        assert c.get('/pronto').status_code == 200
        agora[0] = 30
        assert c.get('/eco').status_code == 200

def test_memoria_limitada_por_origens():
    app = criar(max_ips=3)
    for i in range(100):
        app._permitir(str(i))
        app._registrar_isca(str(i), '/.env')
    assert len(app.baldes) == len(app.ultimas_iscas) == 3

@pytest.mark.parametrize('headers,esperado', [({}, 413),
    ({'content-length': '1'}, 413), ({'content-length': '30'}, 413),
    ({'content-length': 'invalid'}, 400), ({'content-length': '-1'}, 400)])
def test_corpo_real_chunked_ou_tamanho_falso(headers, esperado):
    mensagens = iter([{'type': 'http.request', 'body': b'x' * 12, 'more_body': True},
                      {'type': 'http.request', 'body': b'x' * 12, 'more_body': False}])
    respostas = []
    async def receive():
        return next(mensagens)
    async def send(msg):
        respostas.append(msg)
    scope = {'type': 'http', 'method': 'POST', 'path': '/eco', 'query_string': b'',
             'headers': [(k.encode(), v.encode()) for k, v in headers.items()],
             'client': ('127.0.0.1', 123), 'server': ('testserver', 80), 'scheme': 'http'}
    asyncio.run(criar()(scope, receive, send))
    assert respostas[0]['status'] == esperado

def test_corpo_valido_e_metodo_perigoso():
    with TestClient(criar()) as c:
        assert c.post('/eco', content=b'x' * 20).json() == {'bytes': 20}
        assert c.request('TRACE', '/eco').status_code == 405

def test_host_permitido_e_host_forjado():
    with TestClient(criar(hosts=['testserver'])) as c:
        assert c.get('/eco').status_code == 200
        assert c.get('/eco', headers={'Host': 'attacker.example'}).status_code == 400
        assert c.post('/.env', content=b'x' * 100,
                      headers={'Host': 'attacker.example'}).status_code == 400


def test_isca_integrada_fora_do_openapi(cliente):
    assert cliente.get('/.env').status_code == 404
    esquema = cliente.get('/openapi.json').json()
    assert ISCAS.isdisjoint(esquema['paths'])
    assert cliente.get('/contas').status_code == 401
    assert cliente.get('/pronto').status_code == 200


def test_erros_perimetro_producao_tem_hsts():
    with TestClient(criar(producao=True)) as c:
        assert 'max-age=31536000' in c.get('/.env').headers['strict-transport-security']


def test_traceback_do_servidor_nao_vaza_segredo():
    import sys
    from app.core import logs
    try:
        raise ValueError('senha-secreta-exemplo')
    except ValueError:
        registro = logging.makeLogRecord({'msg': 'Erro ASGI', 'exc_info': sys.exc_info()})
    assert 'senha-secreta' not in logs.FormatoJson().format(registro)
    assert logs._SemDetalhesExcecao().filter(registro)
    assert registro.exc_info is None
    assert registro.tipo_erro == 'ValueError'

@pytest.mark.parametrize('modo,esperado', [('lento', 408), ('memoria', 503), ('desconectado', None)])
def test_envio_lento_ou_memoria_liberam_reserva(modo, esperado):
    app = criar(espera_corpo=0.01, memoria_corpos=8 if modo == 'memoria' else 100)
    respostas = []
    vezes = 0
    async def receive():
        nonlocal vezes
        vezes += 1
        if vezes == 1:
            return {'type': 'http.request', 'body': b'1234', 'more_body': True}
        if modo == 'lento':
            await asyncio.sleep(0.1)
        if modo == 'desconectado':
            return {'type': 'http.disconnect'}
        return {'type': 'http.request', 'body': b'123456', 'more_body': False}
    async def send(msg):
        respostas.append(msg)
    scope = {'type': 'http', 'method': 'POST', 'path': '/eco', 'query_string': b'',
             'headers': [], 'client': ('127.0.0.1', 123), 'server': ('testserver', 80), 'scheme': 'http'}
    asyncio.run(app(scope, receive, send))
    assert app.bytes_em_uso == 0
    if esperado is None:
        assert respostas == []
    else:
        assert respostas[0]['status'] == esperado


@pytest.mark.parametrize('caminho', ['/admin/database', '/api/internal/users',
                                      '/backup/astro.dump', '/actuator/env'])
def test_novas_iscas_nao_chamam_aplicacao_nem_leem_corpo(caminho):
    async def proibido(*args):
        raise AssertionError('A isca não deve acessar aplicação ou corpo.')
    respostas = []
    async def send(msg):
        respostas.append(msg)
    scope = {'type': 'http', 'method': 'POST', 'path': caminho.upper() + '/',
             'query_string': b'token=segredo', 'headers': [],
             'client': ('127.0.0.1', 123), 'server': ('testserver', 80), 'scheme': 'http'}
    asyncio.run(PerimetroHTTP(proibido, limite=20)(scope, proibido, send))
    assert respostas[0]['status'] == 404
    assert b'segredo' not in respostas[1]['body']



def test_prontidao_publica_nao_contorna_limite():
    with TestClient(criar(requisicoes_minuto=2), client=('203.0.113.7', 123)) as c:
        assert c.get('/pronto').status_code == 200
        assert c.get('/pronto').status_code == 200
        assert c.get('/pronto').status_code == 429
