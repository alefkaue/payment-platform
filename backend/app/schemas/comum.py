"""Tipos compartilhados pelos schemas da API.

Dinheiro entra como número ou string e SAI como string decimal ("1234.50") --
o Pydantic v2 serializa Decimal como string no JSON. Assim o app nunca faz
conta de dinheiro em float.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

# Até 2 casas e no máximo 12 dígitos (cabe em Numeric(14,2)). gt=0 rejeita zero/negativo.
Dinheiro = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
DinheiroOuZero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ProvaBiometrica(BaseModel):
    """Resposta a um desafio de POST /biometria/desafios."""

    desafio_id: str = Field(..., min_length=10, max_length=60)
    quadros: list[str] = Field(
        ..., min_length=2, max_length=5,
        description="Imagens em base64 (sem espelhamento): a 1ª de frente, as seguintes durante o movimento pedido.",
    )


class Destino(BaseModel):
    """Para quem vai o dinheiro: uma chave Pix OU agência + número da conta."""

    chave: str | None = Field(default=None, max_length=120)
    agencia: str | None = Field(default=None, max_length=4)
    numero: str | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if bool(self.chave) == bool(self.numero):
            raise ValueError("Informe a chave Pix OU o número da conta (não os dois).")
        return self


class ContaResumo(BaseModel):
    carteira_id: int
    agencia: str
    numero: str
    nome: str | None = None


class ContaResponse(BaseModel):
    carteira_id: int
    agencia: str
    numero: str
    titular_tipo: str
    nome: str | None = None
    documento: str | None = None
    empresa_id: int | None = None
    regime_apuracao: str | None = None
    saldo: Decimal
    saldo_bloqueado: Decimal
    papel: str | None = None
    alcada: Decimal | None = None


class TransacaoResponse(BaseModel):
    id: int
    tipo: str
    origem: ContaResumo
    destino: ContaResumo
    valor_bruto: Decimal
    cbs: Decimal
    ibs: Decimal
    liquido: Decimal
    imposto_total: Decimal
    tipo_destino: str
    aplicou_split: bool
    auth_metodo: str
    status: str
    bloqueio_ate: datetime | None = None
    descricao: str | None = None
    transacao_original_id: int | None = None
    data_hora: datetime


class PendenteResponse(BaseModel):
    """Operação PJ que passou da alçada de quem lançou e espera aprovação."""

    pendente_aprovacao: bool = True
    operacao_id: int
    valor: Decimal
    mensagem: str
