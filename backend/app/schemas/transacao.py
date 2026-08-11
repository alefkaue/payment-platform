from datetime import datetime

from pydantic import BaseModel, Field


class TransacaoCreate(BaseModel):
    origem_usuario_id: int = Field(gt=0)
    destino_usuario_id: int = Field(gt=0)
    valor: float = Field(gt=0)


class TransacaoResponse(BaseModel):
    id: int
    origem_usuario_id: int
    destino_usuario_id: int
    valor: float
    data_hora: datetime
