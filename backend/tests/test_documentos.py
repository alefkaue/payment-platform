import re

from app.core import documentos as d
from tests.helpers import gerar_chave_nfe, gerar_cnpj, gerar_cpf


def test_cpf():
    assert d.cpf_valido(gerar_cpf())
    assert d.cpf_valido("529.982.247-25")
    assert not d.cpf_valido("529.982.247-24")
    assert not d.cpf_valido("111.111.111-11")


def test_cnpj():
    assert d.cnpj_valido(gerar_cnpj())
    assert d.cnpj_valido("11.222.333/0001-81")
    assert not d.cnpj_valido("11.222.333/0001-82")


def test_chave_nfe_e_cnpj_do_emitente():
    cnpj = gerar_cnpj()
    chave = gerar_chave_nfe(cnpj)
    assert d.chave_nfe_valida(chave) and chave[6:20] == cnpj
    errada = chave[:-1] + str((int(chave[-1]) + 1) % 10)
    assert not d.chave_nfe_valida(errada)
    assert not d.chave_nfe_valida(chave[:-1])


def test_numero_conta_tem_digito():
    assert re.fullmatch(r"\d{8}-\d", d.gerar_numero_conta())


def test_mascaras_e_celular():
    assert d.mascarar_nome("Alef Kaue Santos") == "Alef K*** S***"
    assert d.mascarar_cpf("52998224725") == "***.982.247-**"
    assert d.normalizar_celular("(11) 98765-4321") == "+5511987654321"
    assert d.normalizar_celular("123") is None
