"""
Modelos ORM do PayFlow -- v7.

O que mudou em relação à v6 (ver HANDOFF.md, seção "v7"):

- PESSOA x EMPRESA x VÍNCULO. `usuarios` agora é sempre uma pessoa (CPF, login,
  biometria). Empresas ficam em `empresas` (CNPJ, porte, regime de apuração) e
  quem opera cada empresa está em `vinculos` (papel + alçada em R$). Antes a
  mesma linha era a pessoa que faz login E a empresa, o que impedia representante
  legal, vários operadores e dupla aprovação.
- CARTEIRA com titular explícito: PF (usuario_id), PJ (empresa_id) ou SISTEMA
  (`sistema` = CAIXA | TRIBUTOS). Agência + número de conta com dígito; o número
  é gerado pelo banco (antes o usuário escolhia um id de 6 dígitos, fácil de
  adivinhar). `saldo_bloqueado` guarda o que está em bloqueio cautelar.
- A antiga conta "Governo" fazia 3 papéis (admin, emissor de depósitos, destino
  do imposto). Agora: admin = pessoa com papel admin; CAIXA = conta de liquidação
  (emite depósitos/rendimento, pode ficar negativa); TRIBUTOS = conta transitória
  de CBS/IBS, esvaziada pelo repasse diário (`repasses_tributo`).
- SPLIT só em COBRANÇA vinculada a NF-e (`cobrancas.nfe_chave` + cbs/ibs que vêm
  da nota). Transferência comum nunca retém imposto.
- `creditos_tributarios` substitui `carteiras.creditos`: crédito é INFORMAÇÃO
  (consultada ou declarada, com fonte e data), não dinheiro guardado pelo banco.
- Segurança: `dispositivos`, `limites`, `desafios_biometria`, `contestacoes`;
  transação ganhou `status` (concluida | retida | devolvida | devolvida_parcial).
- PJ: `operacoes_pendentes` (dupla aprovação), `chaves_pix`, `autorizacoes_
  recorrentes` (Pix Automático), `webhooks` + `webhook_entregas`,
  `rendimentos` (rendimento diário do saldo).
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Tipo JSON cross-dialect: JSONB no Postgres, JSON genérico no SQLite.
JSONTipo = JSON().with_variant(JSONB(), "postgresql")
Dinheiro = Numeric(14, 2)


class TipoPessoa(str, enum.Enum):
    """Titular de uma carteira (e tipo do destino de uma transação)."""

    PF = "PF"
    PJ = "PJ"
    SISTEMA = "SISTEMA"  # contas internas do banco (CAIXA, TRIBUTOS)


class Papel(str, enum.Enum):
    USUARIO = "usuario"
    ADMIN = "admin"


class AuthMetodo(str, enum.Enum):
    SENHA = "senha"          # abaixo do limite facial: o JWT autoriza
    SELFIE = "selfie"        # acima do limite: exigiu MFA facial com desafio
    APROVACAO = "aprovacao"  # PJ: executada após aprovação de um segundo usuário
    AUTOMATICO = "automatico"  # Pix Automático: autorização prévia do pagador
    SISTEMA = "sistema"      # depósito, rendimento, repasse, devolução


class PapelVinculo(str, enum.Enum):
    ADMIN = "admin"          # sócio/representante: tudo, inclusive gerir vínculos
    APROVADOR = "aprovador"  # aprova operações pendentes até a própria alçada
    OPERADOR = "operador"    # lança operações (acima da alçada viram pendentes)
    CONSULTA = "consulta"    # só vê saldo e extrato


class RegimeApuracao(str, enum.Enum):
    REGULAR = "regular"  # IBS/CBS pelo regime regular -> sujeito ao split
    SIMPLES = "simples"  # Simples Nacional (recolhe pelo DAS) -> sem split por padrão
    MEI = "mei"          # fora da obrigatoriedade do split


class StatusTransacao(str, enum.Enum):
    CONCLUIDA = "concluida"
    RETIDA = "retida"                    # bloqueio cautelar no recebedor
    DEVOLVIDA = "devolvida"              # MED procedente ou estorno total
    DEVOLVIDA_PARCIAL = "devolvida_parcial"


# =============================================================================
# Pessoas, empresas e vínculos
# =============================================================================


class Usuario(Base):
    """Uma PESSOA: faz login, tem biometria e, opcionalmente, uma carteira PF."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # CPF só com dígitos. Nulo apenas para o admin de sistema.
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[Papel] = mapped_column(Enum(Papel, name="papel_usuario"), nullable=False, default=Papel.USUARIO)
    # Template biométrico CIFRADO (Fernet). Nunca a foto, nunca o vetor em texto puro.
    embedding_facial_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    data_nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    celular: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Situação da verificação de identidade: pendente | em_analise | aprovado | reprovado.
    kyc_status: Mapped[str] = mapped_column(String(12), nullable=False, default="pendente")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Pontos PayFlow (PF): ganha comprando na Loja/Viagens, resgata em passagens.
    pontos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vinculos: Mapped[list["Vinculo"]] = relationship(back_populates="usuario", foreign_keys="Vinculo.usuario_id")


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(String(180), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(180), nullable=True)
    porte: Mapped[str] = mapped_column(String(10), nullable=False, default="PME")  # MEI | PME | GRANDE
    regime_apuracao: Mapped[RegimeApuracao] = mapped_column(
        Enum(RegimeApuracao, name="regime_apuracao"), nullable=False, default=RegimeApuracao.REGULAR
    )
    cnae: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Setor informado no cadastro ("Indústria", "Autopeças"...). Usado no simulador.
    setor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    situacao_cadastral: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Quando e por qual provedor o CNPJ foi conferido (ver services/cnpj_service.py).
    verificada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verificada_por: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Representante legal que abriu a conta (pessoa com KYC aprovado). Responde pela
    # empresa perante o banco; os demais usuários entram por convite.
    representante_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # pendente | em_analise | aprovado (KYB: CNPJ + documentos + representante).
    kyb_status: Mapped[str] = mapped_column(String(12), nullable=False, default="pendente")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vinculos: Mapped[list["Vinculo"]] = relationship(back_populates="empresa")


class StatusVinculo(str, enum.Enum):
    PENDENTE = "pendente"      # convite enviado, a pessoa ainda não aceitou
    AGUARDANDO = "aguardando"  # grande empresa: aguarda a aprovação de outro admin
    ATIVO = "ativo"
    SUSPENSO = "suspenso"      # bloqueio temporário (pode reativar)
    REVOGADO = "revogado"      # acesso encerrado
    RECUSADO = "recusado"      # a pessoa recusou o convite


class Vinculo(Base):
    """Acesso de UMA PESSOA à conta de uma empresa, com papel e alçada (valor
    máximo por operação sem aprovação de outra pessoa; nula = sem limite).

    Cada pessoa tem o próprio login, a própria biometria e o próprio vínculo --
    não existe "login da empresa" compartilhado. O admin convida pelo CPF; o
    vínculo nasce PENDENTE e só vira ATIVO quando a dona daquele CPF (com KYC
    aprovado) aceita com o rosto. `ativo` espelha status == ATIVO para as
    consultas de permissão continuarem simples."""

    __tablename__ = "vinculos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "empresa_id", name="uq_vinculo_usuario_empresa"),
        UniqueConstraint("empresa_id", "cpf", name="uq_vinculo_empresa_cpf"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nulo enquanto o convite não for aceito (a pessoa pode nem ter conta ainda).
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    cpf: Mapped[str | None] = mapped_column(String(11), nullable=True, index=True)
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    celular: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    papel: Mapped[PapelVinculo] = mapped_column(Enum(PapelVinculo, name="papel_vinculo"), nullable=False)
    alcada: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=StatusVinculo.ATIVO.value)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_acesso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario | None"] = relationship(back_populates="vinculos", foreign_keys=[usuario_id])
    empresa: Mapped["Empresa"] = relationship(back_populates="vinculos")


# =============================================================================
# Carteiras e movimentação
# =============================================================================


class Carteira(Base):
    __tablename__ = "carteiras"

    id: Mapped[int] = mapped_column(primary_key=True)
    titular_tipo: Mapped[TipoPessoa] = mapped_column(Enum(TipoPessoa, name="tipo_pessoa"), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True, index=True)
    # CAIXA | TRIBUTOS para as contas de sistema; nulo para PF/PJ.
    sistema: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    agencia: Mapped[str] = mapped_column(String(4), nullable=False, default="0001")
    # Número da conta com dígito ("12345678-9"), gerado pelo banco.
    numero: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    saldo: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    # Valor recebido mas em bloqueio cautelar (não pode ser gasto).
    saldo_bloqueado: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario | None"] = relationship()
    empresa: Mapped["Empresa | None"] = relationship()
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="carteira")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    origem_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    destino_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    # transferencia | cobranca | deposito | rendimento | repasse_tributo | devolucao | estorno
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="transferencia")
    # valor_bruto = o que a origem paga. liquido = o que o destino recebe.
    # cbs + ibs = retido para a conta TRIBUTOS (só em cobrança com NF-e).
    valor_bruto: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    cbs: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    ibs: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    liquido: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    tipo_destino: Mapped[TipoPessoa] = mapped_column(Enum(TipoPessoa, name="tipo_pessoa"), nullable=False)
    aplicou_split: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_metodo: Mapped[AuthMetodo] = mapped_column(
        Enum(AuthMetodo, name="auth_metodo"), nullable=False, default=AuthMetodo.SENHA
    )
    status: Mapped[StatusTransacao] = mapped_column(
        Enum(StatusTransacao, name="status_transacao"), nullable=False, default=StatusTransacao.CONCLUIDA
    )
    bloqueio_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Quem disparou (pessoa). Nulo em operações de sistema.
    autor_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Aparelho de onde saiu (soma do teto diário de aparelho novo).
    dispositivo_id: Mapped[int | None] = mapped_column(ForeignKey("dispositivos.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(140), nullable=True)
    verificacao_facial: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    # Devolução/estorno aponta para a transação original.
    transacao_original_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class HistoricoSaldo(Base):
    """Ledger de toda mudança de saldo (livre ou bloqueado)."""

    __tablename__ = "historico_saldo"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    saldo_anterior: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    saldo_novo: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    bloqueado_anterior: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    bloqueado_novo: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    motivo: Mapped[str] = mapped_column(String(40), nullable=False, default="transferencia")
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SplitLiquidacao(Base):
    """Uma linha por perna da divisão (CBS -> TRIBUTOS, IBS -> TRIBUTOS, LIQUIDO
    -> recebedor). As pernas de tributo recebem `repasse_id` quando o repasse
    diário as leva ao fisco."""

    __tablename__ = "split_liquidacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    transacao_id: Mapped[int] = mapped_column(ForeignKey("transacoes.id"), nullable=False, index=True)
    natureza: Mapped[str] = mapped_column(String(20), nullable=False)  # CBS | IBS | LIQUIDO
    carteira_destino_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    repasse_id: Mapped[int | None] = mapped_column(ForeignKey("repasses_tributo.id"), nullable=True, index=True)
    # Perna devolvida ao pagador num estorno antes do repasse.
    estornada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RepasseTributo(Base):
    """Repasse (normalmente D+1) do que está na conta TRIBUTOS para o fisco."""

    __tablename__ = "repasses_tributo"

    id: Mapped[int] = mapped_column(primary_key=True)
    cbs_total: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    ibs_total: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    # Pernas consideradas: criadas antes deste instante.
    corte: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditoTributario(Base):
    """Crédito de IBS/CBS de uma empresa como INFORMAÇÃO (não é dinheiro do banco).
    fonte: declarado (informado pela empresa) | plataforma_publica (consultado na
    Receita/CGIBS, quando houver integração) | estorno (gerado por devolução já
    repassada ao fisco)."""

    __tablename__ = "creditos_tributarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    tributo: Mapped[str] = mapped_column(String(4), nullable=False)  # CBS | IBS
    valor: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consultado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cobranca(Base):
    """Cobrança emitida por uma PJ (Pix com QR dinâmico + boleto). É aqui que o
    split acontece: o pagamento de uma cobrança com NF-e retém a CBS e o IBS
    destacados na nota."""

    __tablename__ = "cobrancas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identificador público (txid do Pix dinâmico), 26-35 caracteres alfanuméricos.
    txid: Mapped[str] = mapped_column(String(35), unique=True, nullable=False, index=True)
    recebedor_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    valor: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(140), nullable=True)
    vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    pagador_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    # Documento fiscal: chave de acesso da NF-e/NFS-e (44 dígitos) e o imposto
    # destacado NELA. O banco não recalcula -- retém o que a nota diz.
    nfe_chave: Mapped[str | None] = mapped_column(String(44), nullable=True, index=True)
    cbs: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    ibs: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    linha_digitavel: Mapped[str] = mapped_column(String(60), nullable=False)
    # aberta | paga | cancelada | estornada
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="aberta")
    grupo_parcelamento: Mapped[str | None] = mapped_column(String(35), nullable=True, index=True)
    parcela_numero: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parcelas_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    autorizacao_id: Mapped[int | None] = mapped_column(ForeignKey("autorizacoes_recorrentes.id"), nullable=True)
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    paga_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutorizacaoRecorrente(Base):
    """Pix Automático: o pagador autoriza uma vez; a empresa gera cobranças até
    `valor_maximo` na periodicidade combinada e elas são pagas sozinhas."""

    __tablename__ = "autorizacoes_recorrentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    recebedor_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    pagador_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(140), nullable=False)
    valor_maximo: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    periodicidade: Mapped[str] = mapped_column(String(10), nullable=False)  # semanal | mensal | anual
    # pendente (aguarda o pagador) | ativa | cancelada | recusada
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pendente")
    aceita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChavePix(Base):
    __tablename__ = "chaves_pix"
    __table_args__ = (UniqueConstraint("tipo", "valor", name="uq_chave_tipo_valor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # cpf | cnpj | email | celular | aleatoria
    valor: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperacaoPendente(Base):
    """Operação PJ acima da alçada de quem lançou: espera a aprovação de outra
    pessoa vinculada (maker-checker)."""

    __tablename__ = "operacoes_pendentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    # transferencia | pagamento_cobranca | folha | acesso (mudança de vínculo)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONTipo, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Grande empresa: valores altos pedem 2 aprovações de pessoas diferentes.
    aprovacoes_necessarias: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # [{"usuario_id": 3, "nome": "...", "em": "..."}] -- quem já aprovou.
    aprovacoes: Mapped[list | None] = mapped_column(JSONTipo, nullable=True)
    criado_por_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    # pendente | aprovada | rejeitada | falhou
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pendente")
    decidido_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resultado: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contestacao(Base):
    """Pedido de devolução de uma transação (espelha o MED do Pix)."""

    __tablename__ = "contestacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    transacao_id: Mapped[int] = mapped_column(ForeignKey("transacoes.id"), nullable=False, unique=True)
    aberta_por_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    motivo: Mapped[str] = mapped_column(String(280), nullable=False)
    # aberta | procedente | improcedente
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="aberta")
    valor_devolvido: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# Segurança
# =============================================================================


class Dispositivo(Base):
    """Aparelho de uma pessoa. Só vira confiável depois de uma verificação facial
    nele; até lá vale o teto de aparelho novo (IN BCB 491/2024)."""

    __tablename__ = "dispositivos"
    __table_args__ = (UniqueConstraint("usuario_id", "id_hash", name="uq_dispositivo_usuario"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    # SHA-256 do id enviado pelo app no header X-Dispositivo-Id.
    id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confiavel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confiavel_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Celular perdido/roubado: bloqueado derruba as sessões dele e recusa novos logins.
    bloqueado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bloqueado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Limite(Base):
    """Limites de saída de uma carteira. Aumento fica agendado (`pendente_*`) até
    `pendente_vigente_em` (carência); redução vale na hora."""

    __tablename__ = "limites"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, unique=True)
    por_transacao: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    diurno: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    noturno: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    pendente_por_transacao: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)
    pendente_diurno: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)
    pendente_noturno: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)
    pendente_vigente_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesafioBiometria(Base):
    """Desafio de liveness gerado pelo SERVIDOR (nonce + ação pedida). A prova
    biométrica só vale com um desafio válido, não expirado e não usado -- o app
    não decide sozinho se o rosto está vivo."""

    __tablename__ = "desafios_biometria"

    id: Mapped[int] = mapped_column(primary_key=True)
    publico_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    acao: Mapped[str] = mapped_column(String(20), nullable=False)  # virar_esquerda | virar_direita
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Refresh tokens emitidos no login. Só o HASH (SHA-256) é guardado."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revogado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    substituido_por: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Sessão = família de refresh tokens (a rotação mantém o mesmo sessao_id).
    # "Encerrar sessão" revoga a família e o access com esse `sid` cai na hora.
    sessao_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    dispositivo_id: Mapped[int | None] = mapped_column(ForeignKey("dispositivos.id"), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessaoMfa(Base):
    """Um registro por TENTATIVA (login, biometria, consulta de chave), sucesso
    ou falha. É a fonte dos rate limits."""

    __tablename__ = "sessoes_mfa"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    referencia: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_sessoes_tipo_criado", "tipo", "criado_em"),)


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    ator: Mapped[str] = mapped_column(String(80), nullable=False)
    acao: Mapped[str] = mapped_column(String(80), nullable=False)
    # Quem e em qual empresa -- é o que permite a trilha "Atividade da empresa".
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# =============================================================================
# Identidade (KYC/KYB)
# =============================================================================


class CasoKyc(Base):
    """Uma verificação de identidade (pessoa) ou de empresa. Documento, rosto e
    autenticação NÃO ficam misturados numa coluna do usuário: cada tentativa vira
    um caso com o resultado de cada checagem."""

    __tablename__ = "kyc_casos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(4), nullable=False)  # pf | pj
    # aprovado | em_analise (precisa de olho humano) | reprovado
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    nivel_risco: Mapped[str] = mapped_column(String(8), nullable=False, default="baixo")
    motivos: Mapped[list | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentoIdentidade(Base):
    """Resultado da análise de um documento de identidade. A IMAGEM não é
    guardada (LGPD: dado sensível sem finalidade de retenção) -- só o SHA-256
    dela, os campos lidos mascarados e o que foi conferido."""

    __tablename__ = "documentos_identidade"

    id: Mapped[int] = mapped_column(primary_key=True)
    caso_id: Mapped[int] = mapped_column(ForeignKey("kyc_casos.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(12), nullable=False)  # rg | cnh | cin | passaporte
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    provedor: Mapped[str] = mapped_column(String(20), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    campos: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    verificacoes: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentoEmpresa(Base):
    """Documento societário enviado na abertura/atualização da conta PJ
    (contrato social, CCMEI, cartão CNPJ, procuração). Guardamos hash, tipo e o que
    foi conferido (ex.: o CNPJ aparece no texto); o arquivo vai para armazenamento
    privado em produção (Blob Storage), nunca para pasta pública."""

    __tablename__ = "documentos_empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    tamanho: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    verificacoes: Mapped[dict | None] = mapped_column(JSONTipo, nullable=True)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Funcionario(Base):
    """Cadastro de funcionários da empresa para a FOLHA. É diferente do vínculo
    (acesso ao app): o funcionário pode não operar a conta. Salário só pode ir
    para a conta PF cujo titular tem ESTE CPF -- o servidor resolve o destino, o
    app não informa conta nenhuma (impede desviar salário para terceiro)."""

    __tablename__ = "funcionarios"
    __table_args__ = (UniqueConstraint("empresa_id", "cpf", name="uq_funcionario_empresa_cpf"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    salario: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    desligado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# =============================================================================
# Integrações e produtos
# =============================================================================


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(300), nullable=False)
    # Segredo para assinar o corpo (HMAC-SHA256). Mostrado só na criação.
    segredo: Mapped[str] = mapped_column(String(80), nullable=False)
    eventos: Mapped[list] = mapped_column(JSONTipo, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEntrega(Base):
    __tablename__ = "webhook_entregas"

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id"), nullable=False, index=True)
    evento: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONTipo, nullable=False)
    # pendente | entregue | falhou
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pendente")
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultima_resposta: Mapped[str | None] = mapped_column(String(300), nullable=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Rendimento(Base):
    """Rendimento creditado numa carteira em um dia útil (um por carteira/dia)."""

    __tablename__ = "rendimentos"
    __table_args__ = (UniqueConstraint("carteira_id", "data", name="uq_rendimento_carteira_dia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    saldo_base: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    taxa_diaria: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Produto(Base):
    """Produto da Loja PayFlow (benefício PF). Vendido por um lojista PJ: a compra
    vira uma cobrança com nota, então tem split como qualquer venda."""

    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str] = mapped_column(String(280), nullable=False)
    preco: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    lojista_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Voo(Base):
    """Passagem do benefício Viagens (PF). Paga em reais (ganha pontos) ou
    resgatada com `milhas` pontos."""

    __tablename__ = "voos"

    id: Mapped[int] = mapped_column(primary_key=True)
    origem: Mapped[str] = mapped_column(String(3), nullable=False)
    origem_cidade: Mapped[str] = mapped_column(String(60), nullable=False)
    destino: Mapped[str] = mapped_column(String(3), nullable=False)
    destino_cidade: Mapped[str] = mapped_column(String(60), nullable=False)
    companhia: Mapped[str] = mapped_column(String(40), nullable=False)
    saida: Mapped[str] = mapped_column(String(5), nullable=False)
    chegada: Mapped[str] = mapped_column(String(5), nullable=False)
    duracao: Mapped[str] = mapped_column(String(10), nullable=False)
    direto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    preco: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False)
    milhas: Mapped[int] = mapped_column(Integer, nullable=False)  # custo em pontos no resgate
    parceiro_carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PontoMovimento(Base):
    """Extrato de pontos: + compra em reais, − resgate de passagem."""

    __tablename__ = "pontos_movimentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String(20), nullable=False)  # compra_loja | compra_voo | resgate_voo
    descricao: Mapped[str] = mapped_column(String(140), nullable=False)
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cartao(Base):
    """Cartão virtual de uma carteira. CVV dinâmico (não persistido); só a
    máscara do número fica guardada (PCI)."""

    __tablename__ = "cartoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras.id"), nullable=False, index=True)
    apelido: Mapped[str] = mapped_column(String(60), nullable=False, default="Cartão virtual")
    numero_masc: Mapped[str] = mapped_column(String(32), nullable=False)
    bandeira: Mapped[str] = mapped_column(String(20), nullable=False, default="Visa")
    validade: Mapped[str] = mapped_column(String(5), nullable=False)  # MM/AA
    virtual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="ativo")
    compras_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    compras_internacionais: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    limite: Mapped[Decimal] = mapped_column(Dinheiro, nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    carteira: Mapped["Carteira"] = relationship(back_populates="cartoes")
