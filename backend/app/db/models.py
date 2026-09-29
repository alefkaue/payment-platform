"""
Modelos ORM para as 8 entidades do DER que vocês definiram:
Usuarios/Empresas, Carteiras, Transacoes, Sessoes/MFA, Historico, Logs_Auditoria,
Split_Regras, Split_Liquidacao.

IMPORTANTE -- não tenho o diagrama DER em si (só os nomes das entidades), então
modelei os campos com base em tudo que já construímos juntos + no que faz sentido
pra cada nome. Pontos que exigem confirmação de vocês, marcados como ASSUNCAO
nos comentários abaixo:

- Usuarios/Empresas: interpretei como UMA tabela (`usuarios`) com um campo
  `tipo` (PF/PJ), já que o motor de Split Payment que vocês descreveram fala
  em "empresa destino" -- não duas tabelas separadas. Ainda não é usado por
  nenhuma lógica hoje (toda conta criada é PF), só deixei o campo pronto.
- Usuarios x Carteiras são tabelas SEPARADAS (1 usuário -> N carteiras),
  batendo com o DER ter as duas como entidades distintas -- mesmo a lógica de
  hoje só criando 1 carteira por usuário no cadastro. Deixa a porta aberta
  pra multi-carteira sem precisar migrar de novo depois.
- `carteiras.chave`: guardada como STRING (não int), pensando na migração
  futura pra chave estilo PIX que vocês pediram. Hoje continua recebendo o
  número que o usuário digita (convertido pra string na gravação) -- a API
  não muda ainda, só o tipo da coluna já fica pronto pra não precisar de
  outra migração quando isso for implementado.
- `Historico` interpretei como um livro-razão de mudança de saldo por
  carteira (saldo_anterior/saldo_novo a cada transação) -- serve pra
  reconciliação/auditoria financeira. Se no DER de vocês "Historico" for
  outra coisa (ex: histórico de login, histórico de dispositivos), me fala
  que eu ajusto.
- `Logs_Auditoria` modelei como log genérico do sistema (ator + ação +
  detalhe em JSON) -- mais amplo que só MFA, cobre qualquer ação
  administrativa futura.
- `Split_Regras` e `Split_Liquidacao`: schema pronto pro motor de split
  (percentuais, natureza do produto, e o registro de cada perna da divisão),
  mas a LÓGICA de calcular/aplicar split ainda não está implementada -- só a
  tabela. Isso fica pro próximo passo que vocês escolherem (loja/viagens).
- Dinheiro: Numeric(14, 2) em vez de float, em TODAS as colunas de valor --
  fecha um problema que eu já tinha sinalizado antes (float perde precisão
  em centavos). Isso muda o tipo devolvido pelo repositório Postgres de
  float para Decimal -- documentado em postgres_repository.py.
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TipoPessoa(str, enum.Enum):
    PF = "PF"
    PJ = "PJ"


class Usuario(Base):
    """Usuarios/Empresas no DER."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[TipoPessoa] = mapped_column(
        Enum(TipoPessoa, name="tipo_pessoa"), nullable=False, default=TipoPessoa.PF
    )
    documento: Mapped[str | None] = mapped_column(String(20), nullable=True)  # CPF/CNPJ -- ainda não exigido
    # Embedding facial (MFA) -- vetor, nunca a foto. Ver services/biometria_service.py.
    embedding_facial: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    carteiras: Mapped[list["Carteira"]] = relationship(back_populates="usuario")


class Carteira(Base):
    __tablename__ = "carteiras"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    # "chave" = o que hoje chamamos de carteira_id na API (o número que o usuário
    # digita). String de propósito -- ver nota no topo do arquivo.
    chave: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario"] = relationship(back_populates="carteiras")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    origem_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    destino_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Guarda o resultado do MFA facial daquela transferência (distancia, limite,
    # confianca, modelo, verificado) -- ver schemas/transacao.py:VerificacaoFacial.
    verificacao_facial: Mapped[dict] = mapped_column(JSONB, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessaoMfa(Base):
    """Sessoes/MFA no DER -- um registro por TENTATIVA de biometria (sucesso ou
    falha), não só pelas que passaram. É a base pra uma central de segurança
    (ver as ideias que discutimos: MFA adaptativo por risco, painel ao vivo)."""

    __tablename__ = "sessoes_mfa"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)  # "cadastro" | "transferencia"
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricoSaldo(Base):
    """Historico no DER -- ledger de toda mudança de saldo (ASSUNCAO, ver nota
    no topo do arquivo)."""

    __tablename__ = "historico_saldo"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    saldo_anterior: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_novo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    ator: Mapped[str] = mapped_column(String(80), nullable=False)  # chave da carteira, "sistema", etc.
    acao: Mapped[str] = mapped_column(String(80), nullable=False)  # "criar_conta" | "transferencia" | ...
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SplitRegra(Base):
    """Schema pronto pro motor de Split Payment -- lógica ainda não implementada."""

    __tablename__ = "split_regras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    natureza_produto: Mapped[str | None] = mapped_column(String(80), nullable=True)
    percentual_destino: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    percentual_taxa: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SplitLiquidacao(Base):
    """Registro de cada perna de uma transação splitada -- lógica ainda não
    implementada, schema pronto para quando o motor de split for construído."""

    __tablename__ = "split_liquidacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    transacao_id: Mapped[int] = mapped_column(ForeignKey("transacoes.id"), nullable=False)
    split_regra_id: Mapped[int | None] = mapped_column(ForeignKey("split_regras.id"), nullable=True)
    carteira_destino_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    valor_liquidado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
