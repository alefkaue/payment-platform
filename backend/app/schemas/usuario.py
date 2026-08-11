from pydantic import BaseModel, Field


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    carteira_id: int = Field(gt=0)
    saldo_inicial: float = Field(default=0.0, ge=0)


class LoginCreate(BaseModel):
    carteira_id: int = Field(gt=0)


class UsuarioResponse(BaseModel):
    id: int
    nome: str
    saldo: float
