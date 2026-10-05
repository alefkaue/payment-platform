from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models import TipoPessoa


class ContaCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    senha: str = Field(..., min_length=8, max_length=72, description="Mínimo 8 caracteres.")
    tipo: TipoPessoa = Field(default=TipoPessoa.PF, description="PF ou PJ (GOV é interno).")
    documento: str | None = Field(default=None, max_length=32, description="CPF (PF) ou CNPJ (PJ).")
    carteira_id: int | None = Field(
        default=None, gt=0, description="ID da carteira. Se omitido, é gerado automaticamente."
    )
    foto_rosto_base64: str = Field(
        ..., min_length=1,
        description="Foto do rosto (base64). Cadastra a biometria (liveness: exige 1 rosto real).",
    )

    @field_validator("tipo")
    @classmethod
    def _sem_gov(cls, v: TipoPessoa) -> TipoPessoa:
        if v == TipoPessoa.GOV:
            raise ValueError("Tipo GOV não é permitido no cadastro.")
        return v


class ContaResponse(BaseModel):
    usuario_id: int
    carteira_id: int
    nome: str
    email: EmailStr
    tipo: TipoPessoa
    documento: str | None = None
    papel: str
    saldo: float
    tem_biometria: bool
