"""Erros de domínio levantados pelo repositório. Os services traduzem cada um
para o HTTPException apropriado -- o repositório não conhece HTTP."""


class SaldoInsuficienteError(Exception):
    """Saldo checado e debitado dentro da MESMA operação atômica
    (executar_movimento), com as carteiras travadas."""


class IdempotenciaConflitanteError(Exception):
    """A Idempotency-Key já foi usada para OUTRA operação (outro destino ou valor).
    Devolver a antiga em silêncio faria o cliente achar que a nova foi feita."""


class EmailDuplicadoError(Exception):
    """e-mail já cadastrado."""


class CpfDuplicadoError(Exception):
    """CPF já cadastrado."""


class CnpjDuplicadoError(Exception):
    """CNPJ já cadastrado."""


class ContaSistemaAusenteError(Exception):
    """Uma conta de sistema (CAIXA, TRIBUTOS, FISCO) não foi criada. Elas são
    criadas no boot (main.py:_preparar)."""


class RostoDuplicadoError(Exception):
    """O rosto corresponde a outra identidade já cadastrada."""


class CadastroFacialIndisponivelError(Exception):
    """Não foi possível conferir todas as identidades faciais existentes."""
