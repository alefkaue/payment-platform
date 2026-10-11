"""Dados fictícios cifrados, busca/uniquidade e preservação da simulação."""
from datetime import date
import base64
import pytest
from sqlalchemy import text
from app.core import dados_pessoais
from app.core.config import get_settings
from app.repositories import get_repository
from tests.helpers import Pessoa, depositar, SENHA


def test_cadastro_nao_deixa_pii_em_sql_e_login_continua(cliente):
    p=Pessoa(cliente,'cifrado@ex.com',nome='Pessoa Fictícia Cifrada')
    repo=get_repository()
    with repo._sf() as s:
        row=s.execute(text('SELECT nome,cpf,email FROM usuarios WHERE id=:id'),{'id':repo.obter_usuario_por_email(p.email)['id']}).one()
    assert all(v.startswith('pii:v1:') for v in row)
    assert p.email not in str(row) and p.cpf not in str(row) and 'Pessoa Fictícia' not in str(row)
    assert repo.obter_usuario_por_login(p.cpf)['email']==p.email
    assert repo.obter_usuario_por_email(p.email)['nome']=='Pessoa Fictícia Cifrada'


def test_cipher_aleatorio_indice_estavel_e_adulteracao_recusada(cliente):
    campo='usuarios.email'
    a=dados_pessoais.cifrar('a@ex.com',campo,'email')
    b=dados_pessoais.cifrar('a@ex.com',campo,'email')
    assert a!=b and a[7:71]==b[7:71]
    assert dados_pessoais.decifrar(a,campo,'email')=='a@ex.com'
    for dado, contexto in [(a,'vinculos.email'),(a[:7]+'f'*64+a[71:],campo),(a[:-5]+'aaaaa',campo)]:
        with pytest.raises(RuntimeError): dados_pessoais.decifrar(dado,contexto,'email')
    with pytest.raises(RuntimeError): dados_pessoais.decifrar('a@ex.com',campo,'email')


def test_rotacao_nao_muda_indice_nem_libera_duplicata(cliente,monkeypatch):
    p=Pessoa(cliente,'rotacao@ex.com')
    s=get_settings()
    anterior=s.pii_keys
    nova=base64.urlsafe_b64encode(bytes([48])*32).decode()
    monkeypatch.setattr(s,'pii_keys',nova+','+anterior)
    assert get_repository().obter_usuario_por_email(p.email)['cpf']==p.cpf
    from scripts.cifrar_dados_pessoais import migrar
    from app.db.base import engine
    with engine.begin() as conn: migrar(conn)
    monkeypatch.setattr(s,'pii_keys',nova)
    assert get_repository().obter_usuario_por_login(p.cpf)['email']==p.email
    from app.repositories.exceptions import EmailDuplicadoError
    with pytest.raises(EmailDuplicadoError):
        get_repository().criar_pessoa(nome='Outro teste',email=p.email,cpf=None,senha_hash='teste',embedding_cifrado=None)


def test_data_json_e_chaves_separadas(cliente,monkeypatch):
    d=date(2001,1,1)
    enc=dados_pessoais.cifrar(d,'usuarios.data_nascimento',formato='data')
    assert dados_pessoais.decifrar(enc,'usuarios.data_nascimento',formato='data')==d
    valor={'nome':'Fictício','cpf':'12345678901'}
    enc=dados_pessoais.cifrar(valor,'documentos_identidade.campos',formato='json')
    assert dados_pessoais.decifrar(enc,'documentos_identidade.campos',formato='json')==valor
    monkeypatch.setattr(get_settings(),'pii_index_key',get_settings().pii_keys)
    with pytest.raises(RuntimeError,match='PII_KEYS'): dados_pessoais.cifrar('teste','usuarios.nome')


def test_mfa_cifrado_mantem_uso_unico(cliente):
    repo=get_repository()
    assert repo.registrar_sessao_mfa(tipo='mfa_usado',sucesso=True,referencia='prova-ficticia-uso-unico')
    assert not repo.registrar_sessao_mfa(tipo='mfa_usado',sucesso=True,referencia='prova-ficticia-uso-unico')


def test_pix_simulado_com_documentos_ficticios_sem_provedor(cliente,monkeypatch):
    import httpx
    def rede_proibida(*_,**__):
        raise AssertionError('Simulação não deve consultar provedor externo.')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',rede_proibida)
    a=Pessoa(cliente,'simulacao-a@ex.com')
    b=Pessoa(cliente,'simulacao-b@ex.com')
    depositar(cliente,a.numero,'20')
    r=a.transferir({'numero':b.numero},'10')
    assert r.status_code==200,r.text
    assert a.saldo()=='10.00' and b.saldo()=='10.00'
