"""Contrato imutável da migração de identidade: valores em forma canônica."""
DDDS_BRASIL = frozenset("11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split())


def _digitos(coluna):
    sql = coluna
    for digito in '0123456789':
        sql = f"replace({sql}, '{digito}', '')"
    return f"{sql} = ''"


CHECKS_IDENTIDADE = {
    'usuarios': [
        ('ck_usuario_cpf_canonico', f"cpf IS NULL OR (length(cpf) = 11 AND {_digitos('cpf')})"),
        ('ck_usuario_celular_canonico',
         "celular IS NULL OR (length(celular) = 14 AND substr(celular, 1, 3) = '+55' "
         "AND substr(celular, 6, 1) = '9' AND " + _digitos('substr(celular, 4)') +
         " AND substr(celular, 4, 2) IN (" + ','.join(f"'{d}'" for d in sorted(DDDS_BRASIL)) + '))'),
    ],
    'empresas': [
        ('ck_empresa_cnpj_canonico', f"length(cnpj) = 14 AND {_digitos('cnpj')}"),
    ],
}
