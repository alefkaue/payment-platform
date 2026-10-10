from datetime import date, datetime
from typing import Annotated
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.documentos import normalizar_celular
from app.db.models import PapelVinculo, RegimeApuracao
from app.schemas.comum import ContaResponse, DinheiroOuZero, ProvaBiometrica
from app.schemas.auth import TokenResponse

# Base64 de imagem/PDF: ~10 MB de arquivo cabem em ~14 MB de texto.
_B64_MAX = 14 * 1024 * 1024


class DocumentoIdentidadeEnvio(BaseModel):
    tipo: str = Field(..., pattern="^(rg|cnh|cin|passaporte)$")
    frente: str = Field(..., min_length=100, max_length=_B64_MAX, description="Imagem (JPG/PNG/WEBP) em base64.")
    verso: str | None = Field(default=None, max_length=_B64_MAX)


class DocumentoEmpresaEnvio(BaseModel):
    tipo: str = Field(..., pattern="^(contrato_social|ccmei|cartao_cnpj|procuracao|outro)$")
    arquivo: str = Field(..., min_length=100, max_length=_B64_MAX, description="PDF ou imagem em base64.")


class PessoaCreate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=120)
    email: EmailStr
    senha: str = Field(..., min_length=1, max_length=128)
    cpf: str = Field(..., min_length=11, max_length=14)
    data_nascimento: date | None = None
    celular: str | None = Field(default=None, max_length=20)
    biometria: ProvaBiometrica
    documento: DocumentoIdentidadeEnvio | None = None


    @field_validator("celular")
    @classmethod
    def celular_valido(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        normalizado = normalizar_celular(valor)
        if normalizado is None:
            raise ValueError("Informe um celular válido: DDD e 9 dígitos começando por 9.")
        return normalizado


class CadastroSessaoCreate(PessoaCreate):
    atestacao: list[Annotated[str, Field(max_length=8000)]] | None = Field(default=None, max_length=8)


class CadastroSessaoResponse(BaseModel):
    conta: ContaResponse
    tokens: TokenResponse


class EmpresaCreate(BaseModel):
    cnpj: str = Field(..., min_length=14, max_length=18)
    razao_social: str | None = Field(default=None, max_length=180)
    nome_fantasia: str | None = Field(default=None, max_length=180)
    porte: str = Field(default="PME", pattern="^(MEI|PME|GRANDE)$")
    setor: str | None = Field(default=None, max_length=80)
    regime_apuracao: RegimeApuracao = RegimeApuracao.REGULAR
    documentos: list[DocumentoEmpresaEnvio] | None = Field(default=None, max_length=5)


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
    representante_usuario_id: int | None = None
    kyb_status: str | None = None


class ConviteCreate(BaseModel):
    """Admin dá acesso a uma PESSOA pelo CPF. Ela aceita com o próprio login."""

    cpf: str = Field(..., min_length=11, max_length=14)
    nome: str = Field(..., min_length=3, max_length=120)
    email: EmailStr | None = None
    celular: str | None = Field(default=None, max_length=20)
    cargo: str | None = Field(default=None, max_length=80, description="Ex.: Financeiro, Contabilidade.")
    papel: PapelVinculo
    alcada: DinheiroOuZero | None = Field(default=None, description="Máximo por operação sem aprovação. Vazio = sem limite.")
    alcada_diaria: DinheiroOuZero | None = Field(
        default=None, description="Soma por dia sem aprovação (≥ alçada). Vazio = igual à alçada.")
    biometria: ProvaBiometrica | None = Field(default=None, description="Rosto de quem concede (papéis/alçadas sensíveis).")


class VinculoUpdate(BaseModel):
    papel: PapelVinculo | None = None
    alcada: DinheiroOuZero | None = None
    alcada_diaria: DinheiroOuZero | None = None
    sem_limite: bool = False
    biometria: ProvaBiometrica | None = None


class AcaoComBiometria(BaseModel):
    biometria: ProvaBiometrica | None = None


class VinculoResponse(BaseModel):
    id: int
    usuario_id: int | None = None
    nome: str | None = None
    email: str | None = None
    cpf: str | None = None
    celular: str | None = None
    cargo: str | None = None
    papel: str
    alcada: Decimal | None = None
    alcada_diaria: Decimal | None = None
    status: str
    ativo: bool
    aceito_em: datetime | None = None
    status_em: datetime | None = None
    ultimo_acesso_em: datetime | None = None
    criado_em: datetime | None = None
    eu: bool = False
    aguardando_aprovacao: bool = False
    operacao_id: int | None = None


class FuncionarioCreate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=120)
    cpf: str = Field(..., min_length=11, max_length=14)
    cargo: str | None = Field(default=None, max_length=80)
    salario: DinheiroOuZero | None = None


class FolhaItem(BaseModel):
    funcionario_id: int
    valor: DinheiroOuZero | None = Field(default=None, description="Vazio = salário cadastrado.")


class FolhaPagar(BaseModel):
    """Só funcionario_id: o DESTINO é a conta PF do CPF do funcionário, resolvida no servidor."""

    itens: list[FolhaItem] = Field(..., min_length=1, max_length=500)
    descricao: str | None = Field(default=None, max_length=100)
    biometria: ProvaBiometrica | None = None
    # Mesmo contrato do Pix. Sem ela, a chave sai da competência (descrição) + funcionário + valor:
    # o mesmo salário da mesma competência não é pago duas vezes por um reenvio.
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64)
