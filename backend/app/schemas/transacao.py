from datetime import datetime

from pydantic import BaseModel, Field


class TransacaoCreate(BaseModel):
    origem_carteira_id: int = Field(..., description="ID da carteira de quem paga")
    destino_carteira_id: int = Field(..., description="ID da carteira de quem recebe")
    valor: float = Field(..., gt=0, description="Valor a ser transferido")
    foto_verificacao_base64: str = Field(
        ...,
        min_length=1,
        description=(
            "Foto do rosto tirada agora (base64, com ou sem prefixo data:image/...;base64,). "
            "É o MFA que autoriza o débito: precisa passar liveness e bater com o rosto "
            "cadastrado na carteira de origem."
        ),
    )


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
    data_hora: datetime
    verificacao_facial: VerificacaoFacial
