from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

# Dinheiro: no máximo 2 casas decimais e teto que cabe em Numeric(14,2) -- fecha o
# item #8 (0,001 virava 0,00; valor gigante estourava a coluna). gt=0 rejeita zero/negativo.
Dinheiro = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class TransferenciaCreate(BaseModel):
    destino_carteira_id: int = Field(..., gt=0, description="Carteira de quem recebe.")
    valor: Dinheiro = Field(..., description="Valor bruto a transferir (reais, 2 casas).")
    # Obrigatória só quando o valor passa do limite facial (ver pagamento_service).
    foto_verificacao_base64: str | None = Field(
        default=None, description="Selfie (base64) para MFA quando o valor exige."
    )
    idempotency_key: str | None = Field(
        default=None, max_length=80,
        description="Chave única opcional: um retry/double-click com a mesma chave não duplica a transferência.",
    )


class DepositoRequest(BaseModel):
    carteira_id: int = Field(..., gt=0)
    valor: Dinheiro = Field(..., description="Valor a creditar (emitido pela conta Governo).")


class VerificacaoFacial(BaseModel):
    verificado: bool
    distancia: float
    limite: float
    confianca: float
    modelo: str


class TransacaoResponse(BaseModel):
    id: int
    origem_carteira_id: int
    destino_carteira_id: int
    valor: float
    valor_bruto: float
    cbs: float
    ibs: float
    liquido: float
    imposto_total: float
    tipo_destino: str
    aplicou_split: bool
    auth_metodo: str
    verificacao_facial: VerificacaoFacial | None = None
    data_hora: datetime


class RetencaoGovernoResponse(BaseModel):
    cbs_total: float
    ibs_total: float
    total: float
    transacoes_com_split: int
