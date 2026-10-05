"""Erros de domínio levantados pelo repositório. Os services traduzem cada um
para o HTTPException apropriado -- o repositório não conhece HTTP."""


class SaldoInsuficienteError(Exception):
    """Saldo checado e debitado dentro da MESMA operação atômica
    (executar_transferencia). É o que fecha a condição de corrida: checar e
    escrever viraram uma coisa só, protegida por SELECT ... FOR UPDATE (Postgres)
    / lock de banco (SQLite)."""


class IdDuplicadoError(Exception):
    """carteira_id (chave) já existe."""


class EmailDuplicadoError(Exception):
    """e-mail já cadastrado."""


class DocumentoDuplicadoError(Exception):
    """CPF/CNPJ já cadastrado."""


class CarteiraGovernoAusenteError(Exception):
    """A conta Governo (destino do imposto) não foi inicializada. Não deveria
    acontecer em runtime -- ela é criada no boot (ver main.py:startup)."""
