from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.db.models import PapelVinculo, RegimeApuracao
from app.schemas.comum import DinheiroOuZero, ProvaBiometrica


class PessoaCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    senha: str = Field(..., min_length=8, max_length=72, description="Mínimo 8 caracteres.")
    cpf: str = Field(..., min_length=11, max_length=14)
    biometria: ProvaBiometrica


class EmpresaCreate(BaseModel):
    cnpj: str = Field(..., min_length=14, max_length=18)
    razao_social: str | None = Field(default=None, max_length=180)
    nome_fantasia: str | None = Field(default=None, max_length=180)
    porte: str = Field(default="PME", pattern="^(MEI|PME|GRANDE)$")
    setor: str | None = Field(default=None, max_length=80)
    regime_apuracao: RegimeApuracao = RegimeApuracao.REGULAR


class EmpresaResponse(BaseModel):
    id: int
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    porte: str
    regime_apuracao: str
    cnae: str | None = None
    setor: str | None = None
    situacao_cadastral: str | None = None
    verificada_por: str | None = None


class VinculoCreate(BaseModel):
    email: EmailStr = Field(..., description="E-mail de uma pessoa que já tem conta na Astro.")
    papel: PapelVinculo
    alcada: DinheiroOuZero | None = Field(default=None, description="Valor máximo por operação sem aprovação. Vazio = sem limite.")


class VinculoResponse(BaseModel):
    id: int
    usuario_id: int
    nome: str | None = None
    email: str | None = None
    papel: str
    alcada: Decimal | None = None
    ativo: bool
