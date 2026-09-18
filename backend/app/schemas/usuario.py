from pydantic import BaseModel, Field


class UsuarioCreate(BaseModel):
    nome: str = Field(..., min_length=1, description="Nome do titular da carteira")
    carteira_id: int = Field(
        ..., gt=0, description="Chave numérica da carteira, escolhida livremente pelo usuário"
    )
    saldo_inicial: float = Field(0.0, ge=0, description="Saldo inicial da carteira")
    foto_rosto_base64: str = Field(
        ...,
        min_length=1,
        description=(
            "Foto do rosto do titular (base64, com ou sem prefixo data:image/...;base64,). "
            "Usada para cadastrar a biometria facial (MFA) da carteira -- exige exatamente "
            "1 rosto real (liveness) na foto."
        ),
    )


class UsuarioResponse(BaseModel):
    carteira_id: int
    nome: str
    saldo: float
