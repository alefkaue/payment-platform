"""
Validação e formatação de documentos e identificadores brasileiros. Funções
puras, sem I/O -- testadas em tests/test_documentos.py.
"""

import re
import secrets
import uuid

_SO_DIGITOS = re.compile(r"\D")


def somente_digitos(valor: str) -> str:
    return _SO_DIGITOS.sub("", valor or "")


def _dv_mod11(base: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(cpf: str) -> bool:
    c = somente_digitos(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    d1 = _dv_mod11(c[:9], list(range(10, 1, -1)))
    d2 = _dv_mod11(c[:9] + str(d1), list(range(11, 1, -1)))
    return c[-2:] == f"{d1}{d2}"


def cnpj_valido(cnpj: str) -> bool:
    c = somente_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    d1 = _dv_mod11(c[:12], p1)
    d2 = _dv_mod11(c[:12] + str(d1), p2)
    return c[-2:] == f"{d1}{d2}"


def chave_nfe_valida(chave: str) -> bool:
    """Chave de acesso de NF-e/NFC-e/NFS-e nacional: 44 dígitos, o último é DV
    módulo 11 com pesos 2..9 da direita para a esquerda."""
    c = somente_digitos(chave)
    if len(c) != 44 or c != chave.strip():
        return False
    base = c[:43]
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(base)))
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return int(c[43]) == dv


def gerar_chave_nfe(cnpj: str, uf: str = "35", modelo: str = "55") -> str:
    """Chave de acesso válida (DV correto) para uma nota emitida por `cnpj`.
    Usada nas vendas da Loja/Viagens, em que o parceiro emite a nota na hora."""
    from datetime import date

    hoje = date.today()
    base = (f"{uf}{hoje:%y%m}{somente_digitos(cnpj)}{modelo}001"
            f"{secrets.randbelow(10**9):09d}1{secrets.randbelow(10**8):08d}")
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(base)))
    resto = soma % 11
    return base + str(0 if resto < 2 else 11 - resto)


def cnpj_com_dv(base12: str) -> str:
    """Completa os 2 dígitos verificadores de um CNPJ de 12 dígitos."""
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _dv_mod11(base12, p1)
    d2 = _dv_mod11(base12 + str(d1), [6] + p1)
    return f"{base12}{d1}{d2}"


def gerar_numero_conta() -> str:
    """Número de conta de 8 dígitos + dígito verificador (módulo 11)."""
    base = f"{secrets.randbelow(10**8):08d}"
    dv = _dv_mod11(base, [9, 8, 7, 6, 5, 4, 3, 2]) % 10
    return f"{base}-{dv}"


def gerar_txid() -> str:
    """txid de Pix dinâmico: 26 a 35 caracteres alfanuméricos."""
    return uuid.uuid4().hex[:32]


def gerar_linha_digitavel(valor_centavos: int) -> str:
    """Linha digitável de boleto SIMULADA (formato visual de 47 dígitos). Não é
    registrável em banco real -- a emissão de boleto de verdade depende de
    convênio com a CIP/Núclea."""
    corpo = f"{secrets.randbelow(10**37):037d}"
    return f"{corpo}{valor_centavos:010d}"


def mascarar_cpf(cpf: str) -> str:
    c = somente_digitos(cpf)
    if len(c) != 11:
        return "***"
    return f"***.{c[3:6]}.{c[6:9]}-**"


def mascarar_cnpj(cnpj: str) -> str:
    c = somente_digitos(cnpj)
    if len(c) != 14:
        return "***"
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"  # CNPJ é público


def mascarar_nome(nome: str) -> str:
    """'Alef Kaue Santos' -> 'Alef K*** S***' (como a consulta de chave Pix)."""
    partes = (nome or "").split()
    if not partes:
        return "***"
    return " ".join([partes[0]] + [p[0] + "***" for p in partes[1:]])


def normalizar_celular(valor: str) -> str | None:
    """Aceita formatos comuns e devolve +55DDDNÚMERO (padrão do DICT)."""
    d = somente_digitos(valor)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11):
        return None
    return f"+55{d}"
