from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.comum import Destino, Dinheiro, ProvaBiometrica


class TransferenciaCreate(BaseModel):
    destino: Destino
    valor: Dinheiro
    descricao: str | None = Field(default=None, max_length=140)
    # Obrigatória quando o valor passa do limite facial.
    biometria: ProvaBiometrica | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)


class LoteItem(BaseModel):
    destino: Destino
    valor: Dinheiro
    descricao: str | None = Field(default=None, max_length=140)
    idempotency_key: str | None = Field(default=None, max_length=80)


class LoteCreate(BaseModel):
    itens: list[LoteItem] = Field(..., min_length=1, max_length=100)
    # Uma prova só para o lote inteiro, exigida se o TOTAL passar do limite facial.
    biometria: ProvaBiometrica | None = None


class LoteItemResultado(BaseModel):
    indice: int
    situacao: str  # concluida | retida | pendente_aprovacao | erro
    transacao_id: int | None = None
    operacao_id: int | None = None
    erro: str | None = None


class DepositoRequest(BaseModel):
    destino: Destino
    valor: Dinheiro


class ContestacaoCreate(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=280)


class DecisaoContestacao(BaseModel):
    procedente: bool


class DecisaoPendente(BaseModel):
    aprovar: bool
    biometria: ProvaBiometrica | None = None


class NotaFiscal(BaseModel):
    """Documento fiscal da operação. CBS e IBS são os valores DESTACADOS na nota."""

    chave: str = Field(..., min_length=44, max_length=44, description="Chave de acesso de 44 dígitos.")
    cbs: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    ibs: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)


class CobrancaCreate(BaseModel):
    valor: Dinheiro
    descricao: str | None = Field(default=None, max_length=140)
    vencimento: date | None = None
    pagador_documento: str | None = Field(default=None, max_length=18)
    nota_fiscal: NotaFiscal | None = None
    parcelas: int = Field(default=1, ge=1, le=12)


class CobrancaResponse(BaseModel):
    id: int
    txid: str
    valor: Decimal
    descricao: str | None = None
    vencimento: date | None = None
    pagador_documento: str | None = None
    nfe_chave: str | None = None
    cbs: Decimal
    ibs: Decimal
    linha_digitavel: str
    pix_copia_e_cola: str
    status: str
    parcela_numero: int
    parcelas_total: int
    grupo_parcelamento: str | None = None
    autorizacao_id: int | None = None
    transacao_id: int | None = None
    paga_em: datetime | None = None
    recebedor_nome: str | None = None
    vai_reter_imposto: bool
    # informativo (2026: mostra, não retém) | retencao | demonstracao (apresentação)
    split_fase: str = "retencao"


class PagarCobranca(BaseModel):
    biometria: ProvaBiometrica | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)


class AutorizacaoCreate(BaseModel):
    pagador: Destino
    descricao: str = Field(..., min_length=3, max_length=140)
    valor_maximo: Dinheiro
    periodicidade: str = Field(..., pattern="^(semanal|mensal|anual)$")


class CobrancaRecorrenteCreate(BaseModel):
    valor: Dinheiro
    vencimento: date
    descricao: str | None = Field(default=None, max_length=140)
    nota_fiscal: NotaFiscal | None = None


class AutorizacaoResponse(BaseModel):
    id: int
    descricao: str
    valor_maximo: Decimal
    periodicidade: str
    status: str
    aceita_em: datetime | None = None
    cancelada_em: datetime | None = None
    recebedor: dict
    pagador: dict


class CreditoCreate(BaseModel):
    tributo: str = Field(..., pattern="^(CBS|IBS)$")
    valor: Dinheiro
    referencia: str | None = Field(default=None, max_length=80)


class WebhookCreate(BaseModel):
    url: str = Field(..., pattern=r"^https://", max_length=300, description="Precisa ser https.")
    eventos: list[str] = Field(..., min_length=1)


class LimiteUpdate(BaseModel):
    por_transacao: Dinheiro | None = None
    diurno: Dinheiro | None = None
    noturno: Dinheiro | None = None


class ChaveCreate(BaseModel):
    tipo: str = Field(..., pattern="^(cpf|cnpj|email|celular|aleatoria)$")
    valor: str | None = Field(default=None, max_length=120, description="Vazio para chave aleatória e para CPF/CNPJ (usa o do titular).")
