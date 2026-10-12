"""Instalação limpa, separação de segredos e reinício de processo em container."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def preparar(pasta):
    for nome in ['install.sh', 'gerar-segredos.sh', 'docker-compose.yml', 'docker-compose.full.yml', 'docker-compose.hub.yml']:
        shutil.copyfile(ROOT / nome, pasta / nome)
    (pasta / 'backend').mkdir()
    (pasta / 'app').mkdir()
    env = os.environ.copy()
    for chave in ['JWT_SECRET', 'EMBEDDING_KEY', 'ADMIN_SENHA', 'WEBHOOK_KEYS', 'PII_KEYS', 'PII_INDEX_KEY', 'DATABASE_CONTEXT_KEY',
                  'POSTGRES_PASSWORD', 'DATABASE_APP_PASSWORD', 'DATABASE_MIGRATION_PASSWORD']:
        env.pop(chave, None)
    return env


def docker_falso(pasta, env):
    binario = pasta / 'bin'
    binario.mkdir()
    caminho = binario / 'docker'
    caminho.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_DOCKER_LOG"\nif [ "$1" = "--version" ]; then echo "Docker version teste"; fi\n')
    caminho.chmod(0o755)
    env['PATH'] = str(binario) + os.pathsep + env['PATH']
    env['FAKE_DOCKER_LOG'] = str(pasta / 'docker.log')


@pytest.mark.parametrize('args', [[], ['--local'], ['--hub']])
def test_instalacao_perfil_segredos_e_idempotencia(tmp_path, args):
    env = preparar(tmp_path)
    docker_falso(tmp_path, env)
    subprocess.run(['bash', 'install.sh', *args], cwd=tmp_path, env=env, check=True, capture_output=True)
    arquivo = tmp_path / '.env.docker'
    antes = arquivo.read_bytes()
    assert arquivo.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600
    valores = dict(l.split('=', 1) for l in antes.decode().splitlines() if '=' in l and not l.startswith('#'))
    assert all(valores[k] for k in ['JWT_SECRET', 'EMBEDDING_KEY', 'ADMIN_SENHA'])
    log = (tmp_path / 'docker.log').read_text()
    assert (' pull' in log) == (args == ['--hub'])
    subprocess.run(['bash', 'install.sh', *args], cwd=tmp_path, env=env, check=True, capture_output=True)
    assert arquivo.read_bytes() == antes


def test_instalacao_preserva_e_importa_somente_segredos_da_api(tmp_path):
    env = preparar(tmp_path)
    docker_falso(tmp_path, env)
    subprocess.run(['sh', 'gerar-segredos.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    arquivo = tmp_path / '.env.docker'
    linhas = arquivo.read_text().splitlines()
    linhas = [l for l in linhas if not l.startswith(('JWT_SECRET=', 'EMBEDDING_KEY='))]
    arquivo.write_text('\n'.join(linhas) + '\n')
    (tmp_path / '.env').write_text('JWT_SECRET=jwt-antigo-ficticio\nEMBEDDING_KEY=chave-antiga-ficticia\nADMIN_SENHA=nao-substituir\nDATABASE_MIGRATION_PASSWORD=nao-importar\n')
    antes = dict(l.split('=', 1) for l in linhas if '=' in l and not l.startswith('#'))
    subprocess.run(['bash', 'install.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    depois = dict(l.split('=', 1) for l in arquivo.read_text().splitlines() if '=' in l and not l.startswith('#'))
    assert depois['JWT_SECRET'] == 'jwt-antigo-ficticio'
    assert depois['EMBEDDING_KEY'] == 'chave-antiga-ficticia'
    assert depois['ADMIN_SENHA'] == antes['ADMIN_SENHA']
    assert depois['DATABASE_MIGRATION_PASSWORD'] == antes['DATABASE_MIGRATION_PASSWORD']


def test_primeiro_env_docker_preserva_segredos_do_env_antigo(tmp_path):
    env = preparar(tmp_path)
    docker_falso(tmp_path, env)
    antigos = {'JWT_SECRET':'jwt-antigo-ficticio', 'EMBEDDING_KEY':'chave-antiga-ficticia', 'ADMIN_SENHA':'admin-antigo-ficticio'}
    (tmp_path / '.env').write_text('\n'.join(k+'='+v for k,v in antigos.items()))
    subprocess.run(['bash', 'install.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    atuais = dict(l.split('=', 1) for l in (tmp_path / '.env.docker').read_text().splitlines() if '=' in l and not l.startswith('#'))
    assert all(atuais[k] == v for k,v in antigos.items())


def test_instalacao_argumento_invalido_nao_cria_segredos(tmp_path):
    env = preparar(tmp_path)
    r = subprocess.run(['bash', 'install.sh', '--invalido'], cwd=tmp_path, env=env, capture_output=True)
    assert r.returncode == 2
    assert not (tmp_path / '.env.docker').exists()


def configuracao(pasta, env):
    if not shutil.which('docker'):
        pytest.skip('requer Docker Compose para resolver configuração')
    r = subprocess.run(['docker', 'compose', 'version'], env=env, capture_output=True)
    if r.returncode:
        pytest.skip('requer Docker Compose v2')
    args = ['docker', 'compose', '--env-file', '.env.docker', '-f', 'docker-compose.yml', '-f', 'docker-compose.full.yml', 'config', '--format', 'json']
    return subprocess.run(args, cwd=pasta, env=env, capture_output=True)


def test_compose_limpo_repassa_segredos_sem_credenciais_administrativas(tmp_path):
    env = preparar(tmp_path)
    subprocess.run(['sh', 'gerar-segredos.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    (tmp_path / '.env').touch()
    r = configuracao(tmp_path, env)
    assert r.returncode == 0
    backend = json.loads(r.stdout)['services']['backend']['environment']
    arquivo = dict(l.split('=', 1) for l in (tmp_path / '.env.docker').read_text().splitlines() if '=' in l and not l.startswith('#'))
    for chave in ['JWT_SECRET', 'EMBEDDING_KEY', 'ADMIN_SENHA']:
        assert backend[chave] == arquivo[chave]
    assert 'POSTGRES_PASSWORD' not in backend
    assert 'DATABASE_MIGRATION_PASSWORD' not in backend
    assert backend['BIOMETRIA_STUB'] == '0'
    assert backend['BIOMETRIA_STUB_CADASTRO'] == '0'
    assert backend['DPOP_OBRIGATORIO'] == '1'
    assert backend['DEPOSITO_DEMO'] == '1'
    assert backend['KYC_DOCUMENTO_OBRIGATORIO'] == '0'


@pytest.mark.parametrize('chave', ['JWT_SECRET', 'EMBEDDING_KEY', 'ADMIN_SENHA'])
def test_compose_recusa_segredo_ausente_em_vez_de_usar_padrao(tmp_path, chave):
    env = preparar(tmp_path)
    subprocess.run(['sh', 'gerar-segredos.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    arquivo = tmp_path / '.env.docker'
    arquivo.write_text('\n'.join(l for l in arquivo.read_text().splitlines() if not l.startswith(chave + '=')))
    (tmp_path / '.env').touch()
    r = configuracao(tmp_path, env)
    assert r.returncode != 0
    assert chave.encode() in r.stderr


@pytest.mark.skipif(os.environ.get('RUN_CONTAINER_INTEGRATION') != '1', reason='requer imagem local construída e Docker em execução')
def test_container_reinicio_preserva_template_facial_e_assinatura_jwt(tmp_path):
    env = preparar(tmp_path)
    subprocess.run(['sh', 'gerar-segredos.sh'], cwd=tmp_path, env=env, check=True, capture_output=True)
    (tmp_path / '.env').touch()
    r = configuracao(tmp_path, env)
    assert r.returncode == 0
    backend = json.loads(r.stdout)['services']['backend']['environment']
    parametros = tmp_path / 'api.env'
    parametros.write_text('\n'.join(k + '=' + v for k, v in backend.items()))
    parametros.chmod(0o600)
    imagem = os.environ.get('TEST_CONTAINER_IMAGE', 'payment-platform-backend:latest')
    args = ['docker', 'run', '--rm', '--read-only', '--cap-drop=ALL', '--security-opt', 'no-new-privileges:true',
            '--network', 'none', '--env-file', str(parametros), '--entrypoint', 'python', imagem]
    primeiro = "import base64,json,jwt; from app.core.security import cifrar_embedding,_jwt_secret; print(json.dumps({'embedding':base64.b64encode(cifrar_embedding([0.1,0.2])).decode(),'token':jwt.encode({'teste':'reinicio'},_jwt_secret(),algorithm='HS256')}))"
    a = subprocess.run([*args, '-c', primeiro], env=env, capture_output=True, check=True)
    segundo = "import base64,json,sys,jwt; from app.core.security import decifrar_embedding,_jwt_secret; d=json.load(sys.stdin); assert decifrar_embedding(base64.b64decode(d['embedding']))['vetor']==[0.1,0.2]; assert jwt.decode(d['token'],_jwt_secret(),algorithms=['HS256'])['teste']=='reinicio'; print('persistencia-ok')"
    b = subprocess.run([*args[:2], '-i', *args[2:], '-c', segundo], env=env, input=a.stdout, capture_output=True, check=True)
    assert b.stdout.strip() == b'persistencia-ok'
