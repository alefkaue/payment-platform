"""Tipos transparentes para a API; somente igualdade nos campos pesquisáveis."""
from sqlalchemy import String, Text, TypeDecorator, func, type_coerce
import re
from app.core import dados_pessoais


class DadoCifrado(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, campo, dominio=None, formato='texto'):
        super().__init__()
        self.campo, self.dominio, self.formato = campo, dominio, formato

    def process_bind_param(self, value, dialect):
        if value is not None:
            if self.campo in {'usuarios.cpf', 'vinculos.cpf', 'funcionarios.cpf'} and not re.fullmatch(r'[0-9]{11}', value):
                raise ValueError('CPF deve estar na forma canônica de 11 dígitos ASCII.')
            if self.campo == 'empresas.cnpj' and not re.fullmatch(r'[0-9]{14}', value):
                raise ValueError('CNPJ deve estar na forma canônica de 14 dígitos ASCII.')
            if self.campo == 'usuarios.celular':
                from app.db.identidade_v1 import DDDS_BRASIL
                if not re.fullmatch(r'\+55[0-9]{2}9[0-9]{8}', value) or value[3:5] not in DDDS_BRASIL:
                    raise ValueError('Celular deve estar na forma canônica brasileira.')
        return dados_pessoais.cifrar(value, self.campo, self.dominio, self.formato)

    def process_result_value(self, value, dialect):
        return dados_pessoais.decifrar(value, self.campo, self.dominio, self.formato)

    class comparator_factory(TypeDecorator.Comparator):
        def _coluna_indice(self):
            tabela = getattr(self.expr, 'table', None)
            nome = getattr(self.expr, 'name', '') + '_indice'
            if tabela is not None and nome in tabela.c:
                return tabela.c[nome]
            return func.substr(type_coerce(self.expr, String), 8, 64)

        def __eq__(self, other):
            if other is None:
                return super().__eq__(other)
            if not self.type.dominio or not isinstance(other, (str, int)):
                raise ValueError('Campo cifrado permite somente igualdade com valor conhecido.')
            return self._coluna_indice() == dados_pessoais.indice(other, self.type.dominio)

        def in_(self, values):
            if not self.type.dominio or not isinstance(values, (list, tuple, set)):
                raise ValueError("Busca cifrada exige lista de valores conhecidos.")
            return self._coluna_indice().in_(
                [dados_pessoais.indice(v, self.type.dominio) for v in values])

        def not_in(self, values):
            return ~self.in_(values)

        def __ne__(self, other):
            return super().__ne__(other) if other is None else ~self.__eq__(other)


# Contrato versionado; migrations importam cópia própria e não modificam o passado.
CAMPOS = {
    'usuarios': {'nome': None, 'cpf': 'cpf', 'email': 'email', 'celular': None, 'data_nascimento': None},
    'empresas': {'cnpj': 'cnpj', 'razao_social': None, 'nome_fantasia': None},
    'vinculos': {'cpf': 'cpf', 'nome': None, 'email': None, 'celular': None},
    'funcionarios': {'cpf': 'cpf', 'nome': None},
    'chaves_pix': {'valor': 'pix'},
    'cobrancas': {'pagador_documento': None, 'descricao': None},
    'transacoes': {'descricao': None, 'verificacao_facial': None},
    'operacoes_pendentes': {'payload': None, 'descricao': None, 'aprovacoes': None, 'resultado': None},
    'autorizacoes_recorrentes': {'descricao': None},
    'contestacoes': {'motivo': None},
    'refresh_tokens': {'ip': None, 'user_agent': None},
    'sessoes_mfa': {'referencia': 'referencia_mfa', 'ip': 'ip_mfa', 'detalhe': None},
    'logs_auditoria': {'ator': None, 'ip': None, 'detalhe': None},
    'kyc_casos': {'motivos': None},
    'documentos_identidade': {'campos': None, 'verificacoes': None},
    'documentos_empresa': {'verificacoes': None},
    'webhook_entregas': {'payload': None, 'ultima_resposta': None},
}
JSON_CAMPOS = {'verificacao_facial', 'payload', 'aprovacoes', 'resultado', 'detalhe', 'motivos', 'campos', 'verificacoes'}


def configurar_modelos(metadata):
    from sqlalchemy import Computed, Column, UniqueConstraint, Index, CheckConstraint
    for tabela, campos in CAMPOS.items():
        t = metadata.tables[tabela]
        for coluna, dominio in campos.items():
            formato = 'data' if coluna == 'data_nascimento' else ('json' if coluna in JSON_CAMPOS else 'texto')
            t.c[coluna].type = DadoCifrado(tabela + '.' + coluna, dominio, formato)
            t.append_constraint(CheckConstraint(
                f"{coluna} IS NULL OR (substr({coluna}, 1, 7) = 'pii:v1:' AND substr({coluna}, 72, 1) = ':' AND length({coluna}) > 170)",
                name=f"ck_pii_{tabela}_{coluna}"))
        # Os hashes gerados não podem divergir do envelope armazenado.
        for coluna, dominio in campos.items():
            if dominio is None:
                continue
            nome = coluna + '_indice'
            t.append_column(Column(nome, String(64), Computed(f"CASE WHEN substr({coluna}, 1, 7) = 'pii:v1:' THEN substr({coluna}, 8, 64) ELSE NULL END", persisted=True)))
            for constraint in list(t.constraints):
                if isinstance(constraint, UniqueConstraint) and coluna in constraint.columns:
                    nomes = [nome if c.name == coluna else c.name for c in constraint.columns]
                    t.constraints.remove(constraint)
                    t.append_constraint(UniqueConstraint(*nomes, name=constraint.name))
            for index in list(t.indexes):
                if any(c.name == coluna for c in index.columns):
                    t.indexes.remove(index)
                    Index(index.name, *[t.c[nome] if c.name == coluna else c for c in index.columns],
                          unique=index.unique, **dict(index.dialect_kwargs))
        for constraint in list(t.constraints):
            if constraint.name in {'ck_usuario_cpf_canonico', 'ck_usuario_celular_canonico', 'ck_empresa_cnpj_canonico'}:
                t.constraints.remove(constraint)
