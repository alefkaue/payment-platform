"""
Modelos ORM do PayFlow. Esta é a v6: o schema ficou "mais concreto" em cima do
DER da v5, incorporando autenticação (login/JWT), split payment de IBS/CBS e as
correções de segurança da auditoria.

Mudanças desta versão em relação à v5 (todas endereçando itens da auditoria):

- `usuarios` agora é uma CONTA DE VERDADE, com credencial de login: `email`
  (único), `senha_hash` (bcrypt, nunca texto puro), `papel` (user/admin) e
  `documento` (CPF/CNPJ) único. `tipo` ganhou o valor GOV (conta Governo/Tesouro
  que recebe o imposto retido no split). Fecha o item #1 (sem autenticação).
- `embedding_facial` virou `embedding_facial_cifrado` (LargeBinary, cifrado com
  Fernet -- ver core/security.py). Antes era um ARRAY(Float) em texto puro. Fecha
  o item #12 (biometria sem criptografia / LGPD).
- `transacoes` ganhou as colunas do split: `valor_bruto`, `cbs`, `ibs`,
  `liquido`, `tipo_destino`, `aplicou_split`, `auth_metodo` e `idempotency_key`
  (único) -- fecha os itens #11 (idempotência) e #13 (split sem cálculo).
- `refresh_tokens`: tabela nova pra rotação/revogação de refresh tokens (guarda só
  o HASH do token, nunca o token em si).
- `split_liquidacoes` agora guarda a `natureza` de cada perna (CBS/IBS/LIQUIDO) e
  tem FK pra transação -- o motor em services/split_service.py grava uma linha por
  perna, tornando a auditoria fiscal reconstruível.
- `historico_saldo` passa a receber TAMBÉM o depósito/saldo inicial (fecha o item
  #6: antes o histórico começava incompleto).

O que continua igual (e por quê): `carteiras` separada de `usuarios` (1 usuário ->
N carteiras, hoje 1), dinheiro em Numeric(14,2) (nunca float), `sessoes_mfa` como
registro de CADA tentativa (agora de fato gravado -- item #5), `logs_auditoria`
como log genérico (agora de fato gravado).
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Tipo JSON cross-dialect: JSONB no Postgres (indexável, binário), JSON genérico
# no SQLite (dev/testes). Assim o MESMO modelo roda nos dois bancos sem mudança.
JSONTipo = JSON().with_variant(JSONB(), "postgresql")


class TipoPessoa(str, enum.Enum):
    PF = "PF"   # pessoa física
    PJ = "PJ"   # pessoa jurídica (sofre retenção de IBS/CBS no recebimento)
    GOV = "GOV"  # conta Governo/Tesouro -- destino do imposto retido


class Papel(str, enum.Enum):
    USUARIO = "usuario"
    ADMIN = "admin"


class AuthMetodo(str, enum.Enum):
    SENHA = "senha"    # transferência abaixo do limite: só o JWT (login) autoriza
    SELFIE = "selfie"  # transferência acima do limite: exigiu MFA facial


class Usuario(Base):
    """Usuarios/Empresas no DER -- agora com credencial de login."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[TipoPessoa] = mapped_column(
        Enum(TipoPessoa, name="tipo_pessoa"), nullable=False, default=TipoPessoa.PF
    )
    # CPF (PF) ou CNPJ (PJ). Único quando presente; GOV pode usar o documento
    # sintético de config (CONTA_GOVERNO_DOCUMENTO).
    documento: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[Papel] = mapped_column(
        Enum(Papel, name="papel_usuario"), nullable=False, default=Papel.USUARIO
    )
    # Template biométrico CIFRADO (Fernet). Nunca a foto, nunca o vetor em texto puro.
    embedding_facial_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    carteiras: Mapped[list["Carteira"]] = relationship(back_populates="usuario")


class Carteira(Base):
    __tablename__ = "carteiras"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    # "chave" = o carteira_id público (o número que o usuário escolhe). String de
    # propósito, pra migrar pra chave estilo PIX sem outra migração.
    chave: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario"] = relationship(back_populates="carteiras")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    origem_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    destino_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    # valor_bruto = o que a origem paga. liquido = o que o destino recebe.
    # cbs + ibs = o que foi retido e enviado à conta Governo (0 se destino não é PJ).
    valor_bruto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cbs: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    ibs: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    liquido: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_destino: Mapped[TipoPessoa] = mapped_column(
        Enum(TipoPessoa, name="tipo_pessoa"), nullable=False
    )
    aplicou_split: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_metodo: Mapped[AuthMetodo] = mapped_column(
        Enum(AuthMetodo, name="auth_metodo"), nullable=False, default=AuthMetodo.SENHA
    )
    # Resultado do MFA facial (quando houve) -- distancia, limite, confianca, modelo.
    verificacao_facial: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    # Chave de idempotência enviada pelo cliente: um retry/double-click com a mesma
    # chave devolve a MESMA transação em vez de criar outra (item #11).
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Refresh tokens emitidos no login. Guardamos só o HASH (SHA-256) do token,
    nunca o token em si. Rotação: a cada /auth/refresh o token usado é marcado
    `revogado` e `substituido_por` aponta pro novo -- se um refresh já usado
    reaparecer, dá pra detectar reuso (possível roubo) e revogar a cadeia."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revogado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    substituido_por: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessaoMfa(Base):
    """Sessoes/MFA no DER -- um registro por TENTATIVA (login OU biometria),
    sucesso ou falha. Agora de fato gravado (item #5) e usado como fonte do
    rate-limit (ver core rate limit em services)."""

    __tablename__ = "sessoes_mfa"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # identificador usado quando ainda não há usuario_id (ex: e-mail no login que falhou)
    referencia: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)  # login|cadastro|transferencia
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_sessoes_tipo_criado", "tipo", "criado_em"),)


class HistoricoSaldo(Base):
    """Ledger de toda mudança de saldo (inclui o depósito inicial -- item #6)."""

    __tablename__ = "historico_saldo"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    saldo_anterior: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_novo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    motivo: Mapped[str] = mapped_column(String(40), nullable=False, default="transferencia")
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    ator: Mapped[str] = mapped_column(String(80), nullable=False)
    acao: Mapped[str] = mapped_column(String(80), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SplitRegra(Base):
    """Alíquotas de IBS/CBS por vigência. Seedadas no boot (ver split_service).
    percentual_* em pontos percentuais (ex: 8.80 = 8,8%)."""

    __tablename__ = "split_regras"

    id: Mapped[int] = mapped_column(primary_key=True)
    vigencia: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # "2026" | "2027"
    descricao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    aliquota_cbs: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    aliquota_ibs: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SplitLiquidacao(Base):
    """Uma linha por perna da divisão de uma transação (CBS -> GOV, IBS -> GOV,
    LIQUIDO -> destino). Torna a divisão fiscal reconstruível pra auditoria."""

    __tablename__ = "split_liquidacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    transacao_id: Mapped[int] = mapped_column(ForeignKey("transacoes.id"), nullable=False, index=True)
    natureza: Mapped[str] = mapped_column(String(20), nullable=False)  # CBS|IBS|LIQUIDO
    carteira_destino_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
