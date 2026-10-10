"""
Repositório único do PayFlow (SQLAlchemy). Roda igual sobre Postgres (produção) e
SQLite (dev/testes). Services e routers nunca tocam a sessão/ORM direto; tudo
que precisa ser atômico (dinheiro) mora aqui.

O coração é `executar_movimento`: debita a origem, credita o destino (no saldo
livre ou no bloqueado), manda o imposto para a conta TRIBUTOS, grava a transação,
as pernas do split e o histórico de saldo -- numa transação de banco só, com
SELECT ... FOR UPDATE nas carteiras envolvidas (ordem fixa por id, sem deadlock).
Checagens que dependem do saldo/uso do período (saldo suficiente, limites) rodam
DENTRO do lock, via o callback `checar`, para duas operações simultâneas não
passarem as duas pelo mesmo limite.
"""

import json
from contextlib import nullcontext
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core import tempo
from app.core.config import get_settings
from app.core.documentos import gerar_numero_conta
from app.db.base import usando_postgres
from app.db.models import (
    AuthMetodo,
    AutorizacaoRecorrente,
    Carteira,
    ChavePix,
    Cobranca,
    Contestacao,
    CreditoTributario,
    DesafioBiometria,
    Dispositivo,
    Empresa,
    HistoricoSaldo,
    Limite,
    LogAuditoria,
    OperacaoPendente,
    Papel,
    PapelVinculo,
    PontoMovimento,
    Produto,
    RefreshToken,
    RegimeApuracao,
    Rendimento,
    RepasseTributo,
    SessaoMfa,
    SplitLiquidacao,
    StatusTransacao,
    TipoPessoa,
    Transacao,
    Usuario,
    Vinculo,
    Voo,
    Webhook,
    WebhookEntrega,
)
from app.repositories.exceptions import (
    CnpjDuplicadoError,
    ContaSistemaAusenteError,
    CpfDuplicadoError,
    EmailDuplicadoError,
    IdempotenciaConflitanteError,
    SaldoInsuficienteError,
)
from app.repositories.extras import RepositorioExtras
from app.services.split_service import ResultadoSplit

ZERO = Decimal("0.00")
SISTEMAS = ("CAIXA", "TRIBUTOS", "FISCO")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite devolve datetime sem fuso; tudo aqui é UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _chaves_equivalentes(chave: str) -> list[str]:
    """A chave e, para chave de cliente ("{carteira}:u:..."), a forma gravada antes do prefixo
    "u:" existir: reenvio de um Pix antigo continua sendo reenvio (C3-02)."""
    return [chave, chave.replace(":u:", ":", 1)] if ":u:" in chave else [chave]


class Repositorio(RepositorioExtras):
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    # =========================================================================
    # Pessoas
    # =========================================================================

    def criar_pessoa(
        self,
        *,
        nome: str,
        email: str,
        cpf: Optional[str],
        senha_hash: str,
        embedding_cifrado: Optional[bytes],
        papel: Papel = Papel.USUARIO,
        com_carteira: bool = True,
        limites_padrao: Optional[dict] = None,
        data_nascimento: Optional[date] = None,
        celular: Optional[str] = None,
        kyc_status: str = "pendente",
    ) -> dict:
        """Cria a pessoa e (opcional) a carteira PF com os limites padrão, numa
        transação só."""
        with self._sf() as s:
            u = Usuario(
                nome=nome, email=email.lower().strip(), cpf=cpf, senha_hash=senha_hash,
                papel=papel, embedding_facial_cifrado=embedding_cifrado,
                data_nascimento=data_nascimento, celular=celular, kyc_status=kyc_status,
            )
            s.add(u)
            try:
                s.flush()
            except IntegrityError as e:
                s.rollback()
                texto = str(e.orig).lower()
                if "cpf" in texto:
                    raise CpfDuplicadoError("Já existe uma conta com esse CPF.") from None
                raise EmailDuplicadoError("Já existe uma conta com esse e-mail.") from None
            carteira = None
            if com_carteira:
                carteira = self._nova_carteira(s, TipoPessoa.PF, usuario_id=u.id)
                if limites_padrao:
                    s.add(Limite(carteira_id=carteira.id, **limites_padrao))
            s.commit()
            if carteira is None:
                return self._usuario_auth_dict(u)
            return self._conta_dict(s, carteira)

    def obter_usuario_por_email(self, email: str) -> Optional[dict]:
        with self._sf() as s:
            u = s.scalar(select(Usuario).where(Usuario.email == email.lower().strip()))
            return self._usuario_auth_dict(u) if u else None

    def obter_usuario_por_login(self, identificador: str) -> Optional[dict]:
        """E-mail ou CPF (com ou sem pontuação)."""
        ident = identificador.strip()
        if "@" in ident:
            return self.obter_usuario_por_email(ident)
        digitos = "".join(ch for ch in ident if ch.isdigit())
        if len(digitos) != 11:
            return None
        with self._sf() as s:
            u = s.scalar(select(Usuario).where(Usuario.cpf == digitos))
            return self._usuario_auth_dict(u) if u else None

    def obter_usuario_por_id(self, usuario_id: int) -> Optional[dict]:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            return self._usuario_auth_dict(u) if u else None

    def obter_embedding_cifrado(self, usuario_id: int) -> Optional[bytes]:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            if u is None or u.embedding_facial_cifrado is None:
                return None
            return bytes(u.embedding_facial_cifrado)

    def garantir_admin(self, *, email: str, senha_hash: str) -> dict:
        existente = self.obter_usuario_por_email(email)
        if existente:
            return existente
        return self.criar_pessoa(
            nome="Administrador Astro", email=email, cpf=None, senha_hash=senha_hash,
            embedding_cifrado=None, papel=Papel.ADMIN, com_carteira=False,
        )

    # =========================================================================
    # Empresas e vínculos
    # =========================================================================

    def criar_empresa(
        self,
        *,
        usuario_id: int,
        cnpj: str,
        razao_social: str,
        nome_fantasia: Optional[str],
        porte: str,
        regime_apuracao: RegimeApuracao,
        cnae: Optional[str],
        situacao_cadastral: Optional[str],
        verificada_por: str,
        limites_padrao: Optional[dict] = None,
        setor: Optional[str] = None,
        kyb_status: str = "pendente",
    ) -> dict:
        """Empresa + carteira PJ + vínculo ADMIN do representante legal (quem
        abriu), numa transação."""
        with self._sf() as s:
            e = Empresa(
                cnpj=cnpj, razao_social=razao_social, nome_fantasia=nome_fantasia, porte=porte,
                regime_apuracao=regime_apuracao, cnae=cnae, setor=setor, situacao_cadastral=situacao_cadastral,
                verificada_em=tempo.agora(), verificada_por=verificada_por,
                representante_usuario_id=usuario_id, kyb_status=kyb_status,
            )
            s.add(e)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                raise CnpjDuplicadoError("Esse CNPJ já tem conta na Astro.") from None
            carteira = self._nova_carteira(s, TipoPessoa.PJ, empresa_id=e.id)
            if limites_padrao:
                s.add(Limite(carteira_id=carteira.id, **limites_padrao))
            rep = s.get(Usuario, usuario_id)
            agora = tempo.agora()
            s.add(Vinculo(usuario_id=usuario_id, empresa_id=e.id, papel=PapelVinculo.ADMIN, alcada=None,
                          cpf=rep.cpf, nome=rep.nome, email=rep.email, cargo="Representante legal",
                          status="ativo", ativo=True, aceito_em=agora, status_em=agora))
            s.commit()
            return self._conta_dict(s, carteira)

    def obter_empresa(self, empresa_id: int) -> Optional[dict]:
        with self._sf() as s:
            e = s.get(Empresa, empresa_id)
            return self._empresa_dict(e) if e else None

    def obter_vinculo(self, usuario_id: int, empresa_id: int) -> Optional[dict]:
        with self._sf() as s:
            v = s.scalar(
                select(Vinculo).where(
                    Vinculo.usuario_id == usuario_id, Vinculo.empresa_id == empresa_id, Vinculo.ativo.is_(True)
                )
            )
            return self._vinculo_dict(v) if v else None

    def criar_ou_atualizar_vinculo(
        self, *, empresa_id: int, usuario_id: int, papel: PapelVinculo, alcada: Optional[Decimal]
    ) -> dict:
        with self._sf() as s:
            v = s.scalar(select(Vinculo).where(Vinculo.usuario_id == usuario_id, Vinculo.empresa_id == empresa_id))
            if v is None:
                v = Vinculo(usuario_id=usuario_id, empresa_id=empresa_id)
                s.add(v)
            v.papel, v.alcada, v.ativo, v.status = papel, alcada, True, "ativo"
            s.commit()
            s.refresh(v)
            return self._vinculo_dict(v)

    def listar_vinculos(self, empresa_id: int) -> list[dict]:
        with self._sf() as s:
            vs = s.scalars(select(Vinculo).where(Vinculo.empresa_id == empresa_id).order_by(Vinculo.id)).all()
            return [self._vinculo_dict(v) for v in vs]

    def desativar_vinculo(self, vinculo_id: int, empresa_id: int) -> bool:
        with self._sf() as s:
            v = s.get(Vinculo, vinculo_id)
            if not v or v.empresa_id != empresa_id:
                return False
            v.ativo = False
            s.commit()
            return True

    def contar_admins_ativos(self, empresa_id: int) -> int:
        with self._sf() as s:
            return int(
                s.scalar(
                    select(func.count(Vinculo.id)).where(
                        Vinculo.empresa_id == empresa_id, Vinculo.ativo.is_(True), Vinculo.papel == PapelVinculo.ADMIN
                    )
                )
                or 0
            )

    # =========================================================================
    # Carteiras
    # =========================================================================

    def _nova_carteira(self, s: Session, titular: TipoPessoa, **kw) -> Carteira:
        for _ in range(20):
            numero = gerar_numero_conta()
            if not s.scalar(select(Carteira.id).where(Carteira.numero == numero)):
                c = Carteira(titular_tipo=titular, numero=numero, saldo=ZERO, saldo_bloqueado=ZERO, **kw)
                s.add(c)
                s.flush()
                return c
        raise RuntimeError("Não foi possível gerar um número de conta livre.")

    def garantir_contas_sistema(self) -> None:
        with self._sf() as s:
            for nome in SISTEMAS:
                if not s.scalar(select(Carteira).where(Carteira.sistema == nome)):
                    self._nova_carteira(s, TipoPessoa.SISTEMA, sistema=nome)
            s.commit()

    def carteira_sistema(self, nome: str) -> dict:
        with self._sf() as s:
            return self._conta_dict(s, self._sistema(s, nome))

    def _sistema(self, s: Session, nome: str) -> Carteira:
        c = s.scalar(select(Carteira).where(Carteira.sistema == nome))
        if c is None:
            raise ContaSistemaAusenteError(nome)
        return c

    def obter_conta(self, carteira_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = s.get(Carteira, carteira_id)
            return self._conta_dict(s, c) if c else None

    def obter_conta_por_numero(self, numero: str, agencia: str = "0001") -> Optional[dict]:
        with self._sf() as s:
            c = s.scalar(select(Carteira).where(Carteira.numero == numero, Carteira.agencia == agencia))
            return self._conta_dict(s, c) if c else None

    def carteira_pf_do_usuario(self, usuario_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = s.scalar(select(Carteira).where(Carteira.usuario_id == usuario_id))
            return self._conta_dict(s, c) if c else None

    def carteira_da_empresa(self, empresa_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = s.scalar(select(Carteira).where(Carteira.empresa_id == empresa_id))
            return self._conta_dict(s, c) if c else None

    def contas_do_usuario(self, usuario_id: int) -> list[dict]:
        """Carteira PF + carteiras PJ das empresas em que a pessoa tem vínculo ativo."""
        with self._sf() as s:
            res = []
            pf = s.scalar(select(Carteira).where(Carteira.usuario_id == usuario_id))
            if pf:
                res.append({**self._conta_dict(s, pf), "papel": None, "alcada": None})
            vs = s.scalars(select(Vinculo).where(Vinculo.usuario_id == usuario_id, Vinculo.ativo.is_(True))).all()
            for v in vs:
                c = s.scalar(select(Carteira).where(Carteira.empresa_id == v.empresa_id))
                if c:
                    res.append({**self._conta_dict(s, c), "papel": v.papel.value, "alcada": v.alcada})
            return res

    def listar_contas(self, *, limite: int = 50, offset: int = 0) -> list[dict]:
        with self._sf() as s:
            cs = s.scalars(select(Carteira).order_by(Carteira.id).limit(limite).offset(offset)).all()
            return [self._conta_dict(s, c) for c in cs]

    def carteiras_para_rendimento(self) -> list[int]:
        with self._sf() as s:
            return list(
                s.scalars(
                    select(Carteira.id).where(
                        Carteira.titular_tipo.in_([TipoPessoa.PF, TipoPessoa.PJ]), Carteira.saldo > 0
                    )
                ).all()
            )

    # =========================================================================
    # Movimentação (atômica)
    # =========================================================================

    @staticmethod
    def _exigir_identidade_financeira(s: Session, carteira: Carteira) -> None:
        """Pendência de KYC/KYB permite acompanhamento, não movimentação real."""
        if not get_settings().em_producao or carteira.titular_tipo == TipoPessoa.SISTEMA:
            return
        if carteira.titular_tipo == TipoPessoa.PF:
            u = s.get(Usuario, carteira.usuario_id)
            if u is None or not u.ativo or u.kyc_status != "aprovado":
                raise ValueError("Identidade do titular ainda não aprovada para movimentação.")
        else:
            e = s.get(Empresa, carteira.empresa_id)
            u = s.get(Usuario, e.representante_usuario_id) if e and e.representante_usuario_id else None
            if (e is None or e.kyb_status != "aprovado" or u is None
                    or not u.ativo or u.kyc_status != "aprovado"):
                raise ValueError("Identidade da empresa/representante ainda não aprovada para movimentação.")

    def executar_movimento(
        self,
        *,
        origem_id: int,
        destino_id: int,
        split: ResultadoSplit,
        tipo: str,
        auth_metodo: AuthMetodo,
        autor_usuario_id: Optional[int] = None,
        dispositivo_id: Optional[int] = None,
        descricao: Optional[str] = None,
        verificacao_facial: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        bloqueio_ate: Optional[datetime] = None,
        permitir_saldo_negativo: bool = False,
        transacao_original_id: Optional[int] = None,
        usar_bloqueado_destino_primeiro: bool = False,
        checar: Optional[Callable[[Session, Carteira], None]] = None,
        cobranca_id: Optional[int] = None,
        evento: Optional[Callable[[dict], tuple[Optional[int], str, dict]]] = None,
    ) -> dict:
        """Move `split.valor_bruto` da origem: o destino recebe `split.liquido`
        (no saldo bloqueado se `bloqueio_ate`), a conta TRIBUTOS recebe cbs+ibs.
        Levanta SaldoInsuficienteError; `checar` pode levantar qualquer erro de
        domínio (limite estourado etc.) -- tudo dentro do lock.

        Outbox: `evento(transacao) -> (empresa_id, nome, payload)` monta o webhook, e as
        entregas são gravadas NA MESMA transação do dinheiro (se o processo cair depois do
        commit, o job de webhooks entrega; se cair antes, nem o dinheiro nem o evento
        existem). Os ids das entregas voltam em `_entregas` (para a entrega imediata)."""
        def repetida(ja: Transacao) -> dict:
            if (ja.origem_carteira_id, ja.destino_carteira_id, ja.valor_bruto, ja.tipo,
                ja.cbs, ja.ibs, ja.liquido, ja.aplicou_split) != (
                origem_id, destino_id, split.valor_bruto, tipo,
                split.cbs, split.ibs, split.liquido, split.aplicou_split):
                raise IdempotenciaConflitanteError()
            if cobranca_id is not None:
                cob_repetida = s.scalar(select(Cobranca.id).where(Cobranca.transacao_id == ja.id))
                if cob_repetida != cobranca_id:
                    raise IdempotenciaConflitanteError()
            return self._transacao_dict(s, ja)

        valores = (split.valor_bruto, split.liquido, split.cbs, split.ibs)
        if any(not v.is_finite() or v != v.quantize(Decimal("0.01")) for v in valores):
            raise ValueError("Valores devem ser finitos e ter no máximo duas casas decimais.")
        if (split.valor_bruto <= 0 or min(split.liquido, split.cbs, split.ibs) < 0
                or split.valor_bruto != split.liquido + split.cbs + split.ibs
                or (not split.aplicou_split and split.imposto_total != 0)
                or (split.aplicou_split and tipo not in ("cobranca", "resgate_pontos")) or origem_id == destino_id):
            raise ValueError("Movimento financeiro inválido.")

        with self._sf() as s:
            if idempotency_key:
                ja = s.scalar(select(Transacao).where(Transacao.idempotency_key.in_(_chaves_equivalentes(idempotency_key))))
                if ja:
                    return repetida(ja)

            ids = {origem_id, destino_id}
            tributos = None
            if split.aplicou_split and split.imposto_total > 0:
                tributos = self._sistema(s, "TRIBUTOS")
                ids.add(tributos.id)
            stmt = select(Carteira).where(Carteira.id.in_(sorted(ids))).order_by(Carteira.id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            cs = {c.id: c for c in s.scalars(stmt).all()}
            origem, destino = cs[origem_id], cs[destino_id]
            if tipo in ("transferencia", "cobranca", "resgate_pontos"):
                self._exigir_identidade_financeira(s, origem)
                self._exigir_identidade_financeira(s, destino)
            if permitir_saldo_negativo and origem.sistema != "CAIXA":
                raise ValueError("Somente a conta CAIXA pode emitir recursos.")
            if idempotency_key:
                # De novo, já com a carteira travada: quem chegou antes com a mesma chave
                # já fez commit enquanto esperávamos o lock (pedidos repetidos em paralelo).
                ja = s.scalar(select(Transacao).where(Transacao.idempotency_key.in_(_chaves_equivalentes(idempotency_key))))
                if ja:
                    return repetida(ja)

            cob = None
            if cobranca_id is not None:
                cob = s.scalar(select(Cobranca).where(Cobranca.id == cobranca_id)
                               .with_for_update().execution_options(populate_existing=True))
                if cob is None or cob.status != "aberta":
                    raise ValueError("Esta cobrança não está mais aberta.")
                if cob.recebedor_carteira_id != destino_id or cob.valor != split.valor_bruto:
                    raise ValueError("Movimento não corresponde à cobrança.")
                if auth_metodo == AuthMetodo.AUTOMATICO:
                    autorizacao = s.scalar(select(AutorizacaoRecorrente).where(
                        AutorizacaoRecorrente.id == cob.autorizacao_id).with_for_update())
                    if (autorizacao is None or autorizacao.status != "ativa"
                            or autorizacao.pagador_carteira_id != origem_id
                            or autorizacao.recebedor_carteira_id != destino_id
                            or split.valor_bruto > autorizacao.valor_maximo):
                        raise ValueError("Autorização recorrente inválida ou cancelada.")
            if checar:
                checar(s, origem)
            if not permitir_saldo_negativo and origem.saldo < split.valor_bruto:
                raise SaldoInsuficienteError()

            agora = tempo.agora()
            self._mover(s, origem, -split.valor_bruto, motivo=tipo)
            if bloqueio_ate is not None:
                self._mover(s, destino, ZERO, bloqueado=split.liquido, motivo=f"{tipo}_retido")
            else:
                self._mover(s, destino, split.liquido, motivo=tipo)
            if tributos is not None:
                self._mover(s, cs[tributos.id], split.imposto_total, motivo="tributo_retido")

            t = Transacao(
                origem_carteira_id=origem.id,
                destino_carteira_id=destino.id,
                tipo=tipo,
                valor_bruto=split.valor_bruto,
                cbs=split.cbs,
                ibs=split.ibs,
                liquido=split.liquido,
                tipo_destino=destino.titular_tipo,
                aplicou_split=split.aplicou_split,
                auth_metodo=auth_metodo,
                status=StatusTransacao.RETIDA if bloqueio_ate else StatusTransacao.CONCLUIDA,
                bloqueio_ate=bloqueio_ate,
                autor_usuario_id=autor_usuario_id,
                dispositivo_id=dispositivo_id,
                descricao=descricao,
                verificacao_facial=verificacao_facial,
                idempotency_key=idempotency_key,
                transacao_original_id=transacao_original_id,
                criado_em=agora,
            )
            s.add(t)
            try:
                s.flush()
            except IntegrityError:
                # Mesma chave gravada por outra conexão no meio do caminho.
                s.rollback()
                if idempotency_key:
                    ja = s.scalar(select(Transacao).where(Transacao.idempotency_key.in_(_chaves_equivalentes(idempotency_key))))
                    if ja:
                        return repetida(ja)
                raise
            if split.aplicou_split:
                s.add(SplitLiquidacao(transacao_id=t.id, natureza="LIQUIDO", carteira_destino_id=destino.id, valor=split.liquido, criado_em=agora))
                if tributos is not None:
                    if split.cbs > 0:
                        s.add(SplitLiquidacao(transacao_id=t.id, natureza="CBS", carteira_destino_id=tributos.id, valor=split.cbs, criado_em=agora))
                    if split.ibs > 0:
                        s.add(SplitLiquidacao(transacao_id=t.id, natureza="IBS", carteira_destino_id=tributos.id, valor=split.ibs, criado_em=agora))
            if cobranca_id is not None:
                cob.status, cob.transacao_id, cob.paga_em = "paga", t.id, agora
            self._vincular_historico(s, t.id)
            entregas = self._enfileirar_webhooks(s, evento(self._transacao_dict(s, t))) if evento else []
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                if idempotency_key:
                    ja = s.scalar(select(Transacao).where(Transacao.idempotency_key.in_(_chaves_equivalentes(idempotency_key))))
                    if ja:
                        return repetida(ja)
                raise
            s.refresh(t)
            r = self._transacao_dict(s, t)
            if evento:
                r["_entregas"] = [e.id for e in entregas]
            return r

    @staticmethod
    def _enfileirar_webhooks(s: Session, ev: tuple[Optional[int], str, dict]) -> list[WebhookEntrega]:
        """Entregas do evento para os webhooks ativos da empresa, na sessão do movimento."""
        empresa_id, nome, payload = ev
        if empresa_id is None:
            return []
        dados = json.loads(json.dumps(payload, default=str))
        entregas = [WebhookEntrega(webhook_id=w.id, evento=nome, payload=dados)
                    for w in s.scalars(select(Webhook).where(Webhook.empresa_id == empresa_id, Webhook.ativo.is_(True))
                                       .order_by(Webhook.id))
                    if nome in (w.eventos or [])]
        s.add_all(entregas)
        s.flush()
        return entregas

    def liberar_bloqueio(self, transacao_id: int, *, _sessao: Session | None = None) -> Optional[dict]:
        """Retida -> concluída: move o valor do saldo bloqueado para o livre."""
        with (nullcontext(_sessao) if _sessao is not None else self._sf()) as s:
            t = s.scalar(select(Transacao).where(Transacao.id == transacao_id).with_for_update())
            if t is None or t.status != StatusTransacao.RETIDA:
                return None
            stmt = select(Carteira).where(Carteira.id == t.destino_carteira_id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            destino = s.scalar(stmt)
            self._mover(s, destino, t.liquido, bloqueado=-t.liquido, motivo="liberacao_bloqueio")
            t.status, t.bloqueio_ate = StatusTransacao.CONCLUIDA, None
            self._vincular_historico(s, t.id)
            if _sessao is None:
                s.commit()
            return self._transacao_dict(s, t)

    def transacoes_retidas_vencidas(self, ate: datetime) -> list[int]:
        with self._sf() as s:
            abertas = select(Contestacao.transacao_id).where(Contestacao.status == "aberta")
            return list(
                s.scalars(
                    select(Transacao.id).where(
                        Transacao.status == StatusTransacao.RETIDA,
                        Transacao.bloqueio_ate <= ate,
                        Transacao.id.not_in(abertas),
                    )
                ).all()
            )

    def devolver(self, *, transacao_id: int, valor_maximo: Decimal, tipo: str, autor_usuario_id: Optional[int],
                 _sessao: Session | None = None) -> dict:
        """Devolve ao pagador até `valor_maximo`, tirando primeiro do que está
        bloqueado (se a transação estava retida) e depois do saldo livre do
        recebedor, sem deixá-lo negativo. Usado pelo MED procedente."""
        with (nullcontext(_sessao) if _sessao is not None else self._sf()) as s:
            t = s.scalar(select(Transacao).where(Transacao.id == transacao_id).with_for_update())
            if t is None or t.status in (StatusTransacao.DEVOLVIDA, StatusTransacao.DEVOLVIDA_PARCIAL):
                return {"valor_devolvido": ZERO, "transacao": None}
            if not valor_maximo.is_finite() or valor_maximo <= 0:
                raise ValueError("Valor de devolução inválido.")
            valor_maximo = min(valor_maximo, t.liquido)
            ids = sorted({t.origem_carteira_id, t.destino_carteira_id})
            stmt = select(Carteira).where(Carteira.id.in_(ids)).order_by(Carteira.id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            cs = {c.id: c for c in s.scalars(stmt).all()}
            origem, destino = cs[t.origem_carteira_id], cs[t.destino_carteira_id]

            do_bloqueado = min(valor_maximo, destino.saldo_bloqueado) if t.status == StatusTransacao.RETIDA else ZERO
            do_livre = min(valor_maximo - do_bloqueado, max(destino.saldo, ZERO))
            total = do_bloqueado + do_livre
            if total <= 0:
                return {"valor_devolvido": ZERO, "transacao": None}

            self._mover(s, destino, -do_livre, bloqueado=-do_bloqueado, motivo=tipo)
            self._mover(s, origem, total, motivo=tipo)
            dev = Transacao(
                origem_carteira_id=destino.id, destino_carteira_id=origem.id, tipo=tipo,
                valor_bruto=total, liquido=total, cbs=ZERO, ibs=ZERO, tipo_destino=origem.titular_tipo,
                aplicou_split=False, auth_metodo=AuthMetodo.SISTEMA, autor_usuario_id=autor_usuario_id,
                transacao_original_id=t.id, criado_em=tempo.agora(),
            )
            s.add(dev)
            s.flush()
            # Sobra bloqueada que não foi devolvida volta para o saldo livre.
            if t.status == StatusTransacao.RETIDA:
                sobra = t.liquido - do_bloqueado
                if sobra > 0 and destino.saldo_bloqueado >= sobra:
                    self._mover(s, destino, sobra, bloqueado=-sobra, motivo="liberacao_bloqueio")
                t.bloqueio_ate = None
            t.status = StatusTransacao.DEVOLVIDA if total >= t.liquido else StatusTransacao.DEVOLVIDA_PARCIAL
            self._vincular_historico(s, dev.id)
            if _sessao is None:
                s.commit()
            return {"valor_devolvido": total, "transacao": self._transacao_dict(s, dev)}

    def estornar_cobranca(self, *, cobranca_id: int, autor_usuario_id: int,
                          evento: Optional[Callable[[dict], tuple[Optional[int], str, dict]]] = None) -> dict:
        """Devolve ao pagador o valor bruto de uma cobrança paga. O recebedor
        devolve o líquido; os tributos ainda não repassados saem da conta
        TRIBUTOS; os já repassados saem do recebedor e viram crédito informado
        (a empresa recupera na apuração)."""
        with self._sf() as s:
            cob = s.get(Cobranca, cobranca_id)
            if cob is None or cob.transacao_id is None:
                raise ValueError("Cobrança não está paga.")
            t = s.scalar(select(Transacao).where(Transacao.id == cob.transacao_id).with_for_update())
            if t.status in (StatusTransacao.DEVOLVIDA, StatusTransacao.DEVOLVIDA_PARCIAL):
                raise ValueError("Pagamento já devolvido; estorno recusado.")
            tributos = self._sistema(s, "TRIBUTOS")
            ids = sorted({t.origem_carteira_id, t.destino_carteira_id, tributos.id})
            stmt = select(Carteira).where(Carteira.id.in_(ids)).order_by(Carteira.id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            cs = {c.id: c for c in s.scalars(stmt).all()}
            pagador, recebedor, trib = cs[t.origem_carteira_id], cs[t.destino_carteira_id], cs[tributos.id]
            cob = s.scalar(select(Cobranca).where(Cobranca.id == cobranca_id)
                           .with_for_update().execution_options(populate_existing=True))
            if cob.status != "paga":
                raise ValueError("Cobrança não está paga.")

            pernas = s.scalars(
                select(SplitLiquidacao).where(
                    SplitLiquidacao.transacao_id == t.id, SplitLiquidacao.natureza.in_(["CBS", "IBS"])
                )
            ).all()
            de_tributos = sum((p.valor for p in pernas if p.repasse_id is None), ZERO)
            ja_repassado = {p.natureza: p.valor for p in pernas if p.repasse_id is not None}
            do_recebedor = t.liquido + sum(ja_repassado.values(), ZERO)
            if recebedor.saldo < do_recebedor:
                raise SaldoInsuficienteError()

            self._mover(s, recebedor, -do_recebedor, motivo="estorno")
            if de_tributos > 0:
                self._mover(s, trib, -de_tributos, motivo="estorno_tributo")
            self._mover(s, pagador, t.valor_bruto, motivo="estorno")
            for p in pernas:
                if p.repasse_id is None:
                    p.estornada = True
            if ja_repassado and recebedor.empresa_id:
                for natureza, valor in ja_repassado.items():
                    s.add(CreditoTributario(
                        empresa_id=recebedor.empresa_id, tributo=natureza, valor=valor,
                        fonte="estorno", referencia=f"cobranca:{cob.txid}",
                    ))
            dev = Transacao(
                origem_carteira_id=recebedor.id, destino_carteira_id=pagador.id, tipo="estorno",
                valor_bruto=t.valor_bruto, liquido=t.valor_bruto, cbs=ZERO, ibs=ZERO,
                tipo_destino=pagador.titular_tipo, aplicou_split=False, auth_metodo=AuthMetodo.SISTEMA,
                autor_usuario_id=autor_usuario_id, transacao_original_id=t.id, criado_em=tempo.agora(),
            )
            s.add(dev)
            s.flush()
            t.status = StatusTransacao.DEVOLVIDA
            cob.status = "estornada"
            self._vincular_historico(s, dev.id)
            entregas = self._enfileirar_webhooks(s, evento(self._transacao_dict(s, dev))) if evento else []
            s.commit()
            r = self._transacao_dict(s, dev)
            if evento:
                r["_entregas"] = [e.id for e in entregas]
            return r

    def _mover(self, s: Session, c: Carteira, delta: Decimal, *, motivo: str, bloqueado: Decimal = ZERO) -> None:
        anterior, bloq_ant = c.saldo, c.saldo_bloqueado
        c.saldo = anterior + delta
        c.saldo_bloqueado = bloq_ant + bloqueado
        # Mantém o histórico fora do flush que gera o id da transação. Caso
        # contrário ele sairia de s.new com transacao_id NULL antes da vinculação.
        s.info.setdefault("historicos_movimento", []).append(HistoricoSaldo(
            carteira_id=c.id, saldo_anterior=anterior, saldo_novo=c.saldo,
            bloqueado_anterior=bloq_ant, bloqueado_novo=c.saldo_bloqueado, motivo=motivo,
        ))

    @staticmethod
    def _vincular_historico(s: Session, transacao_id: int) -> None:
        historicos = s.info.pop("historicos_movimento", [])
        for obj in historicos:
            obj.transacao_id = transacao_id
            s.add(obj)
        if historicos:
            t = s.get(Transacao, transacao_id)
            # Trilha mínima atômica com o dinheiro: mesmo se o log do service
            # ou a entrega de webhook falhar após o commit, este registro existe.
            s.add(LogAuditoria(ator="sistema", acao="movimento_registrado",
                               usuario_id=t.autor_usuario_id, criado_em=tempo.agora(),
                               detalhe={"transacao_id": transacao_id, "tipo": t.tipo,
                                        "carteiras": [h.carteira_id for h in historicos]}))

    # ---- consultas usadas por limites e risco (rodam dentro do lock) ----

    @staticmethod
    def soma_saidas(s: Session, carteira_id: int, desde: datetime, *, dispositivo_id: Optional[int] = None) -> Decimal:
        stmt = select(func.coalesce(func.sum(Transacao.valor_bruto), 0)).where(
            Transacao.origem_carteira_id == carteira_id,
            Transacao.tipo.in_(["transferencia", "cobranca"]),
            Transacao.status != StatusTransacao.DEVOLVIDA,
            Transacao.criado_em >= desde,
        )
        if dispositivo_id is not None:
            stmt = stmt.where(Transacao.dispositivo_id == dispositivo_id)
        return Decimal(s.scalar(stmt) or 0)

    @staticmethod
    def soma_saidas_de_aparelhos_nao_confiaveis(s: Session, carteira_id: int, desde: datetime) -> Decimal:
        """Saídas da carteira feitas de QUALQUER aparelho ainda não confirmado (ou sem aparelho).
        O teto diário de aparelho novo do Pix é agregado entre esses aparelhos: trocar de
        aparelho não abre outro teto."""
        nao_confiaveis = select(Dispositivo.id).where(or_(Dispositivo.confiavel.is_(False), Dispositivo.bloqueado.is_(True)))
        stmt = select(func.coalesce(func.sum(Transacao.valor_bruto), 0)).where(
            Transacao.origem_carteira_id == carteira_id,
            Transacao.tipo.in_(["transferencia", "cobranca"]),
            Transacao.status != StatusTransacao.DEVOLVIDA,
            Transacao.criado_em >= desde,
            or_(Transacao.dispositivo_id.is_(None), Transacao.dispositivo_id.in_(nao_confiaveis)),
        )
        return Decimal(s.scalar(stmt) or 0)

    @staticmethod
    def soma_saidas_do_usuario(s: Session, carteira_id: int, usuario_id: int, desde: datetime) -> Decimal:
        """O que ESTA pessoa tirou desta carteira desde `desde`, sem contar o que foi
        executado por aprovação (já passou por outra pessoa) nem o que foi devolvido."""
        stmt = select(func.coalesce(func.sum(Transacao.valor_bruto), 0)).where(
            Transacao.origem_carteira_id == carteira_id,
            Transacao.autor_usuario_id == usuario_id,
            Transacao.tipo.in_(["transferencia", "cobranca"]),
            Transacao.status != StatusTransacao.DEVOLVIDA,
            Transacao.auth_metodo != AuthMetodo.APROVACAO,
            Transacao.criado_em >= desde,
        )
        return Decimal(s.scalar(stmt) or 0)

    def saidas_do_usuario_hoje(self, carteira_id: int, usuario_id: int) -> Decimal:
        with self._sf() as s:
            return self.soma_saidas_do_usuario(s, carteira_id, usuario_id, tempo.inicio_do_dia(tempo.agora()))

    def ja_transacionou(self, origem_id: int, destino_id: int) -> bool:
        with self._sf() as s:
            return (
                s.scalar(
                    select(func.count(Transacao.id)).where(
                        Transacao.origem_carteira_id == origem_id,
                        Transacao.destino_carteira_id == destino_id,
                        Transacao.status == StatusTransacao.CONCLUIDA,
                    )
                )
                or 0
            ) > 0

    def transacao_por_chave(self, idempotency_key: str) -> Optional[dict]:
        with self._sf() as s:
            t = s.scalar(select(Transacao).where(Transacao.idempotency_key.in_(_chaves_equivalentes(idempotency_key))))
            return self._transacao_dict(s, t) if t else None

    def obter_transacao(self, transacao_id: int) -> Optional[dict]:
        """Uma transação (comprovante), com a contestação (MED) dela, se houver."""
        with self._sf() as s:
            t = s.get(Transacao, transacao_id)
            if not t:
                return None
            c = s.scalar(select(Contestacao).where(Contestacao.transacao_id == t.id))
            return {**self._transacao_dict(s, t),
                    "contestacao": {"status": c.status, "criado_em": _utc(c.criado_em)} if c else None}

    def listar_transacoes(self, *, carteira_id: Optional[int] = None, limite: int = 50, offset: int = 0) -> list[dict]:
        with self._sf() as s:
            stmt = select(Transacao)
            if carteira_id is not None:
                stmt = stmt.where(
                    or_(Transacao.origem_carteira_id == carteira_id, Transacao.destino_carteira_id == carteira_id)
                )
            stmt = stmt.order_by(Transacao.id.desc()).limit(limite).offset(offset)
            return [self._transacao_dict(s, t) for t in s.scalars(stmt).all()]

    # =========================================================================
    # Limites e dispositivos
    # =========================================================================

    def obter_limite(self, carteira_id: int) -> Optional[dict]:
        with self._sf() as s:
            lim = s.scalar(select(Limite).where(Limite.carteira_id == carteira_id))
            if lim is None:
                return None
            self._aplicar_pendente(s, lim)
            s.commit()
            return self._limite_dict(lim)

    @staticmethod
    def _aplicar_pendente(s: Session, lim: Limite) -> None:
        vig = _utc(lim.pendente_vigente_em)
        if vig and vig <= tempo.agora():
            for campo in ("por_transacao", "diurno", "noturno"):
                novo = getattr(lim, f"pendente_{campo}")
                if novo is not None:
                    setattr(lim, campo, novo)
                setattr(lim, f"pendente_{campo}", None)
            lim.pendente_vigente_em = None

    @staticmethod
    def limite_na_sessao(s: Session, carteira_id: int) -> Optional[Limite]:
        lim = s.scalar(select(Limite).where(Limite.carteira_id == carteira_id))
        if lim is not None:
            Repositorio._aplicar_pendente(s, lim)
        return lim

    def salvar_limite(self, carteira_id: int, *, imediatos: dict, pendentes: dict, vigente_em: Optional[datetime]) -> dict:
        with self._sf() as s:
            lim = s.scalar(select(Limite).where(Limite.carteira_id == carteira_id))
            for campo, valor in imediatos.items():
                setattr(lim, campo, valor)
                setattr(lim, f"pendente_{campo}", None)
            for campo, valor in pendentes.items():
                setattr(lim, f"pendente_{campo}", valor)
            if pendentes:
                lim.pendente_vigente_em = vigente_em
            elif not any(getattr(lim, f"pendente_{c}") for c in ("por_transacao", "diurno", "noturno")):
                lim.pendente_vigente_em = None
            lim.atualizado_em = tempo.agora()
            s.commit()
            s.refresh(lim)
            return self._limite_dict(lim)

    def registrar_dispositivo(self, *, usuario_id: int, id_hash: str, nome: Optional[str], confiavel: bool = False,
                              atestacao: Optional[str] = None, atualizar_atestacao: bool = False) -> dict:
        with self._sf() as s:
            d = s.scalar(select(Dispositivo).where(Dispositivo.usuario_id == usuario_id, Dispositivo.id_hash == id_hash))
            agora = tempo.agora()
            if d is None:
                d = Dispositivo(usuario_id=usuario_id, id_hash=id_hash, nome=nome, confiavel=confiavel,
                                confiavel_em=agora if confiavel else None)
                s.add(d)
            elif confiavel and not d.confiavel:
                d.confiavel, d.confiavel_em = True, agora
            d.ultimo_uso = agora
            if nome:
                d.nome = nome
            if atualizar_atestacao:
                d.atestacao, d.atestacao_em = atestacao, agora if atestacao else None
            s.commit()
            s.refresh(d)
            return self._dispositivo_dict(d)

    def marcar_dispositivo_confiavel(self, usuario_id: int, dispositivo_id: int) -> dict:
        with self._sf() as s:
            d = s.get(Dispositivo, dispositivo_id)
            if d.usuario_id != usuario_id:
                raise ValueError("Dispositivo de outra pessoa.")
            d.confiavel, d.confiavel_em = True, tempo.agora()
            s.commit()
            return self._dispositivo_dict(d)

    def obter_dispositivo(self, usuario_id: int, id_hash: str) -> Optional[dict]:
        with self._sf() as s:
            d = s.scalar(select(Dispositivo).where(Dispositivo.usuario_id == usuario_id, Dispositivo.id_hash == id_hash))
            return self._dispositivo_dict(d) if d else None

    def listar_dispositivos(self, usuario_id: int) -> list[dict]:
        with self._sf() as s:
            ds = s.scalars(select(Dispositivo).where(Dispositivo.usuario_id == usuario_id, Dispositivo.removido.is_(False)).order_by(Dispositivo.id)).all()
            return [self._dispositivo_dict(d) for d in ds]

    def remover_dispositivo(self, usuario_id: int, dispositivo_id: int) -> bool:
        with self._sf() as s:
            d = s.get(Dispositivo, dispositivo_id)
            if not d or d.usuario_id != usuario_id or d.removido:
                return False
            d.removido, d.bloqueado, d.confiavel = True, True, False
            d.bloqueado_em = tempo.agora()
            s.commit()
            return True

    # =========================================================================
    # Biometria (desafios)
    # =========================================================================

    def criar_desafio(self, *, publico_id: str, acao: str, usuario_id: Optional[int], expira_em: datetime) -> None:
        with self._sf() as s:
            s.add(DesafioBiometria(publico_id=publico_id, acao=acao, usuario_id=usuario_id, expira_em=expira_em))
            s.commit()

    def consumir_desafio(self, publico_id: str) -> Optional[dict]:
        """Marca como usado e devolve; None se não existe ou já foi usado. O
        UPDATE condicional garante uso único mesmo com requisições simultâneas."""
        with self._sf() as s:
            d = s.scalar(select(DesafioBiometria).where(DesafioBiometria.publico_id == publico_id))
            if d is None or d.usado:
                return None
            linhas = s.query(DesafioBiometria).filter(
                DesafioBiometria.id == d.id, DesafioBiometria.usado.is_(False)
            ).update({"usado": True})
            s.commit()
            if linhas != 1:
                return None
            return {"acao": d.acao, "usuario_id": d.usuario_id, "expira_em": _utc(d.expira_em)}

    # =========================================================================
    # Chaves Pix
    # =========================================================================

    def criar_chave(self, *, carteira_id: int, tipo: str, valor: str) -> Optional[dict]:
        with self._sf() as s:
            k = ChavePix(carteira_id=carteira_id, tipo=tipo, valor=valor)
            s.add(k)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return None
            s.refresh(k)
            return {"id": k.id, "tipo": k.tipo, "valor": k.valor, "criado_em": k.criado_em}

    def listar_chaves(self, carteira_id: int) -> list[dict]:
        with self._sf() as s:
            ks = s.scalars(select(ChavePix).where(ChavePix.carteira_id == carteira_id).order_by(ChavePix.id)).all()
            return [{"id": k.id, "tipo": k.tipo, "valor": k.valor, "criado_em": k.criado_em} for k in ks]

    def contar_chaves(self, carteira_id: int) -> int:
        with self._sf() as s:
            return int(s.scalar(select(func.count(ChavePix.id)).where(ChavePix.carteira_id == carteira_id)) or 0)

    def remover_chave(self, carteira_id: int, chave_id: int) -> bool:
        with self._sf() as s:
            k = s.get(ChavePix, chave_id)
            if not k or k.carteira_id != carteira_id:
                return False
            s.delete(k)
            s.commit()
            return True

    def buscar_chave(self, tipo: str, valor: str) -> Optional[int]:
        with self._sf() as s:
            return s.scalar(select(ChavePix.carteira_id).where(ChavePix.tipo == tipo, ChavePix.valor == valor))

    # =========================================================================
    # Cobranças e Pix Automático
    # =========================================================================

    def criar_cobrancas(self, linhas: list[dict]) -> list[dict]:
        with self._sf() as s:
            objs = [Cobranca(**l) for l in linhas]
            chaves = sorted({c.nfe_chave for c in objs if c.nfe_chave})
            if chaves:
                # Trava a carteira de quem cobra: duas emissões simultâneas com a mesma nota
                # não passam juntas. Nota já usada em cobrança não cancelada = recusa (R1-39):
                # senão o mesmo imposto da nota seria retido de novo.
                s.scalar(select(Carteira).where(Carteira.id.in_({c.recebedor_carteira_id for c in objs}))
                         .with_for_update())
                if s.scalar(select(func.count(Cobranca.id)).where(
                        Cobranca.nfe_chave.in_(chaves), Cobranca.status != "cancelada")):
                    raise ValueError("Esta nota fiscal já está vinculada a outra cobrança.")
            ids_autorizacoes = sorted({c.autorizacao_id for c in objs if c.autorizacao_id is not None})
            for aid in ids_autorizacoes:
                a = s.scalar(select(AutorizacaoRecorrente).where(AutorizacaoRecorrente.id == aid).with_for_update())
                if a is None or a.status != "ativa":
                    raise ValueError("A autorização não está ativa.")
                existentes = list(s.scalars(select(Cobranca).where(
                    Cobranca.autorizacao_id == aid, Cobranca.status != "cancelada")))
                def periodo(d):
                    if a.periodicidade == "semanal":
                        return tuple(d.isocalendar()[:2])
                    if a.periodicidade == "mensal":
                        return (d.year, d.month)
                    return (d.year,)
                for c in (c for c in objs if c.autorizacao_id == aid):
                    if (c.recebedor_carteira_id != a.recebedor_carteira_id or c.valor > a.valor_maximo
                            or c.vencimento is None):
                        raise ValueError("Cobrança fora da autorização recorrente.")
                    if any(e.vencimento and periodo(e.vencimento) == periodo(c.vencimento) for e in existentes):
                        raise ValueError("Já existe cobrança desta autorização neste período.")
                    existentes.append(c)
            s.add_all(objs)
            s.commit()
            return [self._cobranca_dict(s, c) for c in objs]

    def obter_cobranca(self, *, txid: Optional[str] = None, cobranca_id: Optional[int] = None) -> Optional[dict]:
        with self._sf() as s:
            if txid is not None:
                c = s.scalar(select(Cobranca).where(Cobranca.txid == txid))
            else:
                c = s.get(Cobranca, cobranca_id)
            return self._cobranca_dict(s, c) if c else None

    def listar_cobrancas(self, recebedor_carteira_id: int, *, status: Optional[str] = None, limite: int = 50, offset: int = 0) -> list[dict]:
        with self._sf() as s:
            stmt = select(Cobranca).where(Cobranca.recebedor_carteira_id == recebedor_carteira_id)
            if status:
                stmt = stmt.where(Cobranca.status == status)
            stmt = stmt.order_by(Cobranca.id.desc()).limit(limite).offset(offset)
            return [self._cobranca_dict(s, c) for c in s.scalars(stmt).all()]

    def cancelar_cobranca(self, cobranca_id: int) -> bool:
        with self._sf() as s:
            n = s.query(Cobranca).filter(Cobranca.id == cobranca_id, Cobranca.status == "aberta").update({"status": "cancelada"})
            s.commit()
            return n == 1

    def cobrancas_recorrentes_vencidas(self, ate: date) -> list[dict]:
        with self._sf() as s:
            stmt = (
                select(Cobranca)
                .join(AutorizacaoRecorrente, AutorizacaoRecorrente.id == Cobranca.autorizacao_id)
                .where(Cobranca.status == "aberta", Cobranca.vencimento <= ate, AutorizacaoRecorrente.status == "ativa")
                .order_by(Cobranca.id)
            )
            return [self._cobranca_dict(s, c) for c in s.scalars(stmt).all()]

    def cobrancas_da_autorizacao(self, autorizacao_id: int) -> list[dict]:
        with self._sf() as s:
            cs = s.scalars(
                select(Cobranca).where(Cobranca.autorizacao_id == autorizacao_id, Cobranca.status != "cancelada")
            ).all()
            return [self._cobranca_dict(s, c) for c in cs]

    def criar_autorizacao(self, **kw) -> dict:
        with self._sf() as s:
            a = AutorizacaoRecorrente(**kw)
            s.add(a)
            s.commit()
            return self._autorizacao_dict(s, a)

    def obter_autorizacao(self, autorizacao_id: int) -> Optional[dict]:
        with self._sf() as s:
            a = s.get(AutorizacaoRecorrente, autorizacao_id)
            return self._autorizacao_dict(s, a) if a else None

    def atualizar_autorizacao(self, autorizacao_id: int, **campos) -> dict:
        with self._sf() as s:
            a = s.scalar(select(AutorizacaoRecorrente).where(AutorizacaoRecorrente.id == autorizacao_id).with_for_update())
            if campos.get("status") in ("ativa", "recusada") and a.status != "pendente":
                raise ValueError("Autorização já decidida ou cancelada.")
            for k, v in campos.items():
                setattr(a, k, v)
            s.commit()
            return self._autorizacao_dict(s, a)

    def listar_autorizacoes(self, carteira_id: int) -> list[dict]:
        with self._sf() as s:
            as_ = s.scalars(
                select(AutorizacaoRecorrente)
                .where(or_(AutorizacaoRecorrente.pagador_carteira_id == carteira_id,
                           AutorizacaoRecorrente.recebedor_carteira_id == carteira_id))
                .order_by(AutorizacaoRecorrente.id.desc())
            ).all()
            return [self._autorizacao_dict(s, a) for a in as_]

    # =========================================================================
    # Operações pendentes (dupla aprovação)
    # =========================================================================

    def criar_pendente(self, *, empresa_id: int, tipo: str, valor: Decimal, payload: dict, criado_por: int,
                       descricao: Optional[str] = None, aprovacoes_necessarias: int = 1,
                       idempotency_key: Optional[str] = None) -> dict:
        """Com chave: o reenvio devolve a pendência que já existe (C2-05); a mesma chave
        para outra operação (tipo ou valor diferentes) é IdempotenciaConflitanteError."""
        def existente(s: Session) -> Optional[dict]:
            if not idempotency_key:
                return None
            ja = s.scalar(select(OperacaoPendente).where(OperacaoPendente.empresa_id == empresa_id,
                                                         OperacaoPendente.idempotency_key == idempotency_key))
            if ja is None:
                return None
            # O pedido inteiro tem de ser o mesmo (destino, txid, itens), não só tipo e valor (C3-01).
            sem_motivo = lambda d: {k: v for k, v in (d or {}).items() if k != "motivo"}
            if ja.tipo != tipo or ja.valor != valor or sem_motivo(ja.payload) != sem_motivo(payload):
                raise IdempotenciaConflitanteError()
            return {**self._pendente_dict(ja), "_entregas": [], "_repetida": True}

        with self._sf() as s:
            if (ja := existente(s)) is not None:
                return ja
            p = OperacaoPendente(empresa_id=empresa_id, tipo=tipo, valor=valor, payload=payload, criado_por_usuario_id=criado_por,
                                 descricao=descricao, aprovacoes_necessarias=aprovacoes_necessarias, aprovacoes=[],
                                 criado_em=tempo.agora(), idempotency_key=idempotency_key)
            s.add(p)
            try:
                s.flush()
            except IntegrityError:
                # Mesma chave gravada por outra requisição ao mesmo tempo.
                s.rollback()
                if (ja := existente(s)) is not None:
                    return ja
                raise
            # Outbox: o aviso "operacao.pendente" nasce no mesmo commit da pendência.
            entregas = self._enfileirar_webhooks(s, (empresa_id, "operacao.pendente", {
                "operacao_id": p.id, "tipo": tipo, "valor": valor}))
            s.commit()
            r = self._pendente_dict(p)
            r["_entregas"] = [e.id for e in entregas]
            return r

    def obter_pendente(self, pendente_id: int) -> Optional[dict]:
        with self._sf() as s:
            p = s.get(OperacaoPendente, pendente_id)
            return self._pendente_dict(p) if p else None

    def listar_pendentes(self, empresa_id: int, status: Optional[str] = "pendente") -> list[dict]:
        with self._sf() as s:
            stmt = select(OperacaoPendente).where(OperacaoPendente.empresa_id == empresa_id)
            if status:
                stmt = stmt.where(OperacaoPendente.status == status)
            return [self._pendente_dict(p) for p in s.scalars(stmt.order_by(OperacaoPendente.id.desc())).all()]

    def expirar_pendentes(self, empresa_id: int, criadas_antes: datetime) -> int:
        """pendente -> expirada para o que ninguém decidiu a tempo."""
        with self._sf() as s:
            n = s.query(OperacaoPendente).filter(
                OperacaoPendente.empresa_id == empresa_id, OperacaoPendente.status == "pendente",
                OperacaoPendente.criado_em < criadas_antes,
            ).update({"status": "expirada", "decidido_em": tempo.agora()}, synchronize_session=False)
            s.commit()
            return int(n)

    def reservar_pendente(self, pendente_id: int, decidido_por: int, novo_status: str) -> bool:
        """pendente -> novo_status, só uma vez (UPDATE condicional)."""
        with self._sf() as s:
            n = s.query(OperacaoPendente).filter(
                OperacaoPendente.id == pendente_id, OperacaoPendente.status == "pendente"
            ).update({"status": novo_status, "decidido_por_usuario_id": decidido_por, "decidido_em": tempo.agora()})
            s.commit()
            return n == 1

    def concluir_pendente(self, pendente_id: int, status: str, resultado: dict) -> None:
        with self._sf() as s:
            p = s.get(OperacaoPendente, pendente_id)
            p.status, p.resultado = status, resultado
            s.commit()

    # =========================================================================
    # Contestações (MED)
    # =========================================================================

    def criar_contestacao(self, *, transacao_id: int, usuario_id: int, motivo: str) -> Optional[dict]:
        with self._sf() as s:
            c = Contestacao(transacao_id=transacao_id, aberta_por_usuario_id=usuario_id, motivo=motivo)
            s.add(c)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return None
            return self._contestacao_dict(c)

    def obter_contestacao(self, contestacao_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = s.get(Contestacao, contestacao_id)
            return self._contestacao_dict(c) if c else None

    def listar_contestacoes(self, status: Optional[str] = None) -> list[dict]:
        with self._sf() as s:
            stmt = select(Contestacao)
            if status:
                stmt = stmt.where(Contestacao.status == status)
            return [self._contestacao_dict(c) for c in s.scalars(stmt.order_by(Contestacao.id)).all()]

    def resolver_contestacao(self, contestacao_id: int, *, procedente: bool, autor_usuario_id: int) -> Optional[dict]:
        """Decisão, devolução/liberação e estado do MED no mesmo commit."""
        with self._sf() as s:
            c = s.get(Contestacao, contestacao_id)
            if c is None:
                return None
            # Mesma ordem dos locks que os demais caminhos de devolução/liberação.
            t = s.scalar(select(Transacao).where(Transacao.id == c.transacao_id).with_for_update())
            c = s.scalar(select(Contestacao).where(Contestacao.id == contestacao_id)
                         .with_for_update().execution_options(populate_existing=True))
            if c.status != "aberta":
                return None
            devolvido = ZERO
            if procedente:
                devolvido = self.devolver(transacao_id=t.id, valor_maximo=t.liquido, tipo="devolucao",
                                         autor_usuario_id=autor_usuario_id, _sessao=s)["valor_devolvido"]
            elif t.status == StatusTransacao.RETIDA:
                self.liberar_bloqueio(t.id, _sessao=s)
            c.status = "procedente" if procedente else "improcedente"
            c.valor_devolvido, c.decidida_em = devolvido, tempo.agora()
            s.commit()
            return self._contestacao_dict(c)

    def fechar_contestacao(self, contestacao_id: int, *, status: str, valor_devolvido: Decimal) -> bool:
        with self._sf() as s:
            n = s.query(Contestacao).filter(Contestacao.id == contestacao_id, Contestacao.status == "aberta").update(
                {"status": status, "valor_devolvido": valor_devolvido, "decidida_em": tempo.agora()}
            )
            s.commit()
            return n == 1

    # =========================================================================
    # Tributos
    # =========================================================================

    def repassar_tributos(self, corte: datetime) -> Optional[dict]:
        """Leva ao FISCO as pernas CBS/IBS criadas antes de `corte` e ainda não
        repassadas nem estornadas."""
        with self._sf() as s:
            trib, fisco = self._sistema(s, "TRIBUTOS"), self._sistema(s, "FISCO")
            stmt = select(Carteira).where(Carteira.id.in_(sorted([trib.id, fisco.id]))).order_by(Carteira.id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            s.scalars(stmt).all()
            pernas = s.scalars(
                select(SplitLiquidacao).where(
                    SplitLiquidacao.natureza.in_(["CBS", "IBS"]),
                    SplitLiquidacao.repasse_id.is_(None),
                    SplitLiquidacao.estornada.is_(False),
                    SplitLiquidacao.criado_em < corte,
                )
            ).all()
            if not pernas:
                return None
            cbs = sum((p.valor for p in pernas if p.natureza == "CBS"), ZERO)
            ibs = sum((p.valor for p in pernas if p.natureza == "IBS"), ZERO)
            rep = RepasseTributo(cbs_total=cbs, ibs_total=ibs, corte=corte)
            s.add(rep)
            s.flush()
            for p in pernas:
                p.repasse_id = rep.id
            self._mover(s, trib, -(cbs + ibs), motivo="repasse_tributo")
            self._mover(s, fisco, cbs + ibs, motivo="repasse_tributo")
            t = Transacao(
                origem_carteira_id=trib.id, destino_carteira_id=fisco.id, tipo="repasse_tributo",
                valor_bruto=cbs + ibs, liquido=cbs + ibs, cbs=cbs, ibs=ibs, tipo_destino=TipoPessoa.SISTEMA,
                aplicou_split=False, auth_metodo=AuthMetodo.SISTEMA, descricao=f"Repasse #{rep.id}",
                criado_em=tempo.agora(),
            )
            s.add(t)
            s.flush()
            self._vincular_historico(s, t.id)
            s.commit()
            return {"id": rep.id, "cbs_total": cbs, "ibs_total": ibs, "total": cbs + ibs, "corte": corte, "pernas": len(pernas)}

    def resumo_tributos(self, *, recebedor_carteira_id: Optional[int] = None, desde: Optional[datetime] = None,
                        ate: Optional[datetime] = None) -> dict:
        with self._sf() as s:
            base = select(SplitLiquidacao).where(SplitLiquidacao.natureza.in_(["CBS", "IBS"]), SplitLiquidacao.estornada.is_(False))
            if desde is not None:
                base = base.where(SplitLiquidacao.criado_em >= desde)
            if ate is not None:
                base = base.where(SplitLiquidacao.criado_em < ate)
            if recebedor_carteira_id is not None:
                base = base.join(Transacao, Transacao.id == SplitLiquidacao.transacao_id).where(
                    Transacao.destino_carteira_id == recebedor_carteira_id
                )
            pernas = s.scalars(base).all()
            def soma(nat, repassada):
                return sum((p.valor for p in pernas if p.natureza == nat and (p.repasse_id is not None) == repassada), ZERO)
            return {
                "cbs_retido": soma("CBS", False) + soma("CBS", True),
                "ibs_retido": soma("IBS", False) + soma("IBS", True),
                "cbs_repassado": soma("CBS", True),
                "ibs_repassado": soma("IBS", True),
                "a_repassar": soma("CBS", False) + soma("IBS", False),
                "transacoes_com_split": len({p.transacao_id for p in pernas}),
            }

    def faturamento_cobrancas(self, recebedor_carteira_id: int, desde: datetime, ate: datetime) -> Decimal:
        """Soma das cobranças pagas no período (vendas recebidas), calculada no servidor."""
        with self._sf() as s:
            return Decimal(s.scalar(select(func.coalesce(func.sum(Cobranca.valor), 0)).where(
                Cobranca.recebedor_carteira_id == recebedor_carteira_id, Cobranca.status == "paga",
                Cobranca.paga_em >= desde, Cobranca.paga_em < ate)) or 0).quantize(Decimal("0.01"))

    def registrar_credito(self, *, empresa_id: int, tributo: str, valor: Decimal, fonte: str, referencia: Optional[str]) -> dict:
        with self._sf() as s:
            c = CreditoTributario(empresa_id=empresa_id, tributo=tributo, valor=valor, fonte=fonte, referencia=referencia)
            s.add(c)
            s.commit()
            return {"id": c.id, "tributo": c.tributo, "valor": c.valor, "fonte": c.fonte, "referencia": c.referencia, "consultado_em": c.consultado_em}

    def listar_creditos(self, empresa_id: int) -> list[dict]:
        with self._sf() as s:
            cs = s.scalars(select(CreditoTributario).where(CreditoTributario.empresa_id == empresa_id).order_by(CreditoTributario.id)).all()
            return [{"id": c.id, "tributo": c.tributo, "valor": c.valor, "fonte": c.fonte, "referencia": c.referencia, "consultado_em": c.consultado_em} for c in cs]

    # =========================================================================
    # Rendimento
    # =========================================================================

    def creditar_rendimento(self, *, carteira_id: int, data: date, taxa_diaria: Decimal, calcular: Callable[[Decimal], Decimal]) -> Optional[dict]:
        """Credita o rendimento do dia (uma vez por carteira/dia) a partir do CAIXA."""
        with self._sf() as s:
            if s.scalar(select(Rendimento.id).where(Rendimento.carteira_id == carteira_id, Rendimento.data == data)):
                return None
            caixa = self._sistema(s, "CAIXA")
            stmt = select(Carteira).where(Carteira.id.in_(sorted([carteira_id, caixa.id]))).order_by(Carteira.id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            cs = {c.id: c for c in s.scalars(stmt).all()}
            c = cs[carteira_id]
            if s.scalar(select(Rendimento.id).where(Rendimento.carteira_id == carteira_id, Rendimento.data == data)):
                return None
            valor = calcular(c.saldo)
            if valor <= 0:
                return None
            self._mover(s, cs[caixa.id], -valor, motivo="rendimento")
            self._mover(s, c, valor, motivo="rendimento")
            s.add(Rendimento(carteira_id=c.id, data=data, saldo_base=c.saldo - valor, valor=valor, taxa_diaria=taxa_diaria))
            t = Transacao(
                origem_carteira_id=caixa.id, destino_carteira_id=c.id, tipo="rendimento", valor_bruto=valor,
                liquido=valor, cbs=ZERO, ibs=ZERO, tipo_destino=c.titular_tipo, aplicou_split=False,
                auth_metodo=AuthMetodo.SISTEMA, descricao=f"Rendimento {data.isoformat()}", criado_em=tempo.agora(),
            )
            s.add(t)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                return None
            self._vincular_historico(s, t.id)
            s.commit()
            return {"carteira_id": carteira_id, "valor": valor}

    def listar_rendimentos(self, carteira_id: int, limite: int = 30) -> list[dict]:
        with self._sf() as s:
            rs = s.scalars(select(Rendimento).where(Rendimento.carteira_id == carteira_id).order_by(Rendimento.data.desc()).limit(limite)).all()
            return [{"data": r.data, "saldo_base": r.saldo_base, "valor": r.valor, "taxa_diaria": r.taxa_diaria} for r in rs]

    # =========================================================================
    # Benefícios PF: Loja, Viagens e pontos
    # =========================================================================

    def garantir_lojista(self, *, cnpj: str, nome: str, setor: str) -> int:
        """Empresa parceira (sem vínculo de pessoa) com carteira PJ. Idempotente.
        Devolve o id da carteira."""
        with self._sf() as s:
            e = s.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
            if e is None:
                e = Empresa(cnpj=cnpj, razao_social=nome, nome_fantasia=nome, porte="PME", setor=setor,
                            regime_apuracao=RegimeApuracao.REGULAR, situacao_cadastral="ATIVA",
                            verificada_em=tempo.agora(), verificada_por="parceiro")
                s.add(e)
                s.flush()
                self._nova_carteira(s, TipoPessoa.PJ, empresa_id=e.id)
                s.commit()
            return s.scalar(select(Carteira.id).where(Carteira.empresa_id == e.id))

    def catalogo_vazio(self) -> bool:
        with self._sf() as s:
            return not s.scalar(select(func.count(Produto.id))) and not s.scalar(select(func.count(Voo.id)))

    def criar_catalogo(self, produtos: list[dict], voos: list[dict]) -> None:
        with self._sf() as s:
            s.add_all([Produto(**p) for p in produtos] + [Voo(**v) for v in voos])
            s.commit()

    def listar_produtos(self) -> list[dict]:
        with self._sf() as s:
            ps = s.scalars(select(Produto).where(Produto.ativo.is_(True)).order_by(Produto.id)).all()
            return [self._produto_dict(s, p) for p in ps]

    def obter_produto(self, produto_id: int) -> Optional[dict]:
        with self._sf() as s:
            p = s.get(Produto, produto_id)
            return self._produto_dict(s, p) if p and p.ativo else None

    def listar_voos(self, *, origem: Optional[str] = None, destino: Optional[str] = None) -> list[dict]:
        with self._sf() as s:
            stmt = select(Voo).where(Voo.ativo.is_(True))
            if origem:
                stmt = stmt.where(Voo.origem == origem)
            if destino:
                stmt = stmt.where(Voo.destino == destino)
            return [self._voo_dict(s, v) for v in s.scalars(stmt.order_by(Voo.id)).all()]

    def obter_voo(self, voo_id: int) -> Optional[dict]:
        with self._sf() as s:
            v = s.get(Voo, voo_id)
            return self._voo_dict(s, v) if v and v.ativo else None

    def mover_pontos(self, *, usuario_id: int, delta: int, motivo: str, descricao: str,
                     transacao_id: Optional[int] = None) -> int:
        """Credita/debita pontos com o usuário travado. Levanta ValueError se o
        débito deixaria o saldo negativo. Devolve o novo saldo."""
        with self._sf() as s:
            stmt = select(Usuario).where(Usuario.id == usuario_id)
            if usando_postgres():
                stmt = stmt.with_for_update().execution_options(populate_existing=True)
            u = s.scalar(stmt)
            if u.pontos + delta < 0:
                raise ValueError("Pontos insuficientes.")
            u.pontos += delta
            s.add(PontoMovimento(usuario_id=usuario_id, delta=delta, motivo=motivo, descricao=descricao,
                                 transacao_id=transacao_id, criado_em=tempo.agora()))
            s.commit()
            return u.pontos

    def extrato_pontos(self, usuario_id: int, limite: int = 50) -> dict:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            ms = s.scalars(select(PontoMovimento).where(PontoMovimento.usuario_id == usuario_id)
                           .order_by(PontoMovimento.id.desc()).limit(limite)).all()
            return {"saldo": u.pontos, "movimentos": [
                {"id": m.id, "delta": m.delta, "motivo": m.motivo, "descricao": m.descricao,
                 "transacao_id": m.transacao_id, "data_hora": _utc(m.criado_em)} for m in ms]}

    def _produto_dict(self, s: Session, p: Produto) -> dict:
        loja = self._conta_dict(s, s.get(Carteira, p.lojista_carteira_id))
        return {"id": p.id, "nome": p.nome, "descricao": p.descricao, "preco": p.preco, "categoria": p.categoria,
                "emoji": p.emoji, "merchant_carteira_id": p.lojista_carteira_id, "merchant_nome": loja["nome"]}

    def _voo_dict(self, s: Session, v: Voo) -> dict:
        parceiro = self._conta_dict(s, s.get(Carteira, v.parceiro_carteira_id))
        return {"id": v.id, "origem": v.origem, "origemCidade": v.origem_cidade, "destino": v.destino,
                "destinoCidade": v.destino_cidade, "companhia": v.companhia, "saida": v.saida,
                "chegada": v.chegada, "duracao": v.duracao, "direto": v.direto, "preco": v.preco,
                "milhas": v.milhas, "merchant_carteira_id": v.parceiro_carteira_id,
                "merchant_nome": parceiro["nome"]}

    # =========================================================================
    # Webhooks
    # =========================================================================

    def criar_webhook(self, *, empresa_id: int, url: str, segredo: str, eventos: list[str]) -> dict:
        with self._sf() as s:
            w = Webhook(empresa_id=empresa_id, url=url, segredo=segredo, eventos=eventos)
            s.add(w)
            s.commit()
            return self._webhook_dict(w)

    def listar_webhooks(self, empresa_id: int, *, so_ativos: bool = False) -> list[dict]:
        with self._sf() as s:
            stmt = select(Webhook).where(Webhook.empresa_id == empresa_id)
            if so_ativos:
                stmt = stmt.where(Webhook.ativo.is_(True))
            return [self._webhook_dict(w) for w in s.scalars(stmt.order_by(Webhook.id)).all()]

    def desativar_webhook(self, empresa_id: int, webhook_id: int) -> bool:
        with self._sf() as s:
            w = s.get(Webhook, webhook_id)
            if not w or w.empresa_id != empresa_id:
                return False
            w.ativo = False
            s.commit()
            return True

    def obter_webhook_com_segredo(self, webhook_id: int) -> Optional[dict]:
        with self._sf() as s:
            w = s.get(Webhook, webhook_id)
            return {**self._webhook_dict(w), "segredo": w.segredo} if w else None

    def entregas_pendentes(self, max_tentativas: int) -> list[dict]:
        with self._sf() as s:
            es = s.scalars(
                select(WebhookEntrega).where(WebhookEntrega.status != "entregue", WebhookEntrega.tentativas < max_tentativas)
                .order_by(WebhookEntrega.id)
            ).all()
            return [self._entrega_dict(e) for e in es]

    def obter_entrega(self, entrega_id: int) -> Optional[dict]:
        with self._sf() as s:
            e = s.get(WebhookEntrega, entrega_id)
            return self._entrega_dict(e) if e else None

    def registrar_tentativa_entrega(self, entrega_id: int, *, sucesso: bool, resposta: str, max_tentativas: int) -> None:
        with self._sf() as s:
            e = s.get(WebhookEntrega, entrega_id)
            e.tentativas += 1
            e.ultima_resposta = resposta[:300]
            e.atualizado_em = tempo.agora()
            e.status = "entregue" if sucesso else ("falhou" if e.tentativas >= max_tentativas else "pendente")
            s.commit()

    def listar_entregas(self, empresa_id: int, limite: int = 50) -> list[dict]:
        with self._sf() as s:
            es = s.scalars(
                select(WebhookEntrega).join(Webhook, Webhook.id == WebhookEntrega.webhook_id)
                .where(Webhook.empresa_id == empresa_id).order_by(WebhookEntrega.id.desc()).limit(limite)
            ).all()
            return [self._entrega_dict(e) for e in es]

    # =========================================================================
    # Refresh tokens
    # =========================================================================

    def salvar_refresh(self, *, usuario_id: int, jti: str, token_hash: str, expira_em: datetime,
                       sessao_id: Optional[str] = None, dispositivo_id: Optional[int] = None,
                       ip: Optional[str] = None, user_agent: Optional[str] = None,
                       token_anterior: Optional[str] = None) -> bool:
        with self._sf() as s:
            # Uma única rotação por token. O lock do usuário serializa também
            # revogação/logout: uma rotação não recria sessão encerrada.
            s.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update())
            if token_anterior:
                anterior = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_anterior).with_for_update())
                if anterior is None or anterior.revogado or anterior.usuario_id != usuario_id:
                    s.query(RefreshToken).filter(RefreshToken.usuario_id == usuario_id).update({"revogado": True})
                    s.commit()
                    return False
                anterior.revogado, anterior.substituido_por = True, jti
            s.add(RefreshToken(usuario_id=usuario_id, jti=jti, token_hash=token_hash, expira_em=expira_em,
                               sessao_id=sessao_id, dispositivo_id=dispositivo_id, ip=ip,
                               user_agent=(user_agent or "")[:200] or None, criado_em=tempo.agora()))
            s.commit()
            return True

    def obter_refresh(self, token_hash: str) -> Optional[dict]:
        with self._sf() as s:
            rt = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            if not rt:
                return None
            return {"id": rt.id, "usuario_id": rt.usuario_id, "jti": rt.jti, "revogado": rt.revogado,
                    "expira_em": rt.expira_em, "substituido_por": rt.substituido_por, "sessao_id": rt.sessao_id,
                    "dispositivo_id": rt.dispositivo_id, "ip": rt.ip, "user_agent": rt.user_agent}

    def revogar_refresh(self, jti: str, substituido_por: Optional[str] = None) -> None:
        with self._sf() as s:
            rt = s.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
            if rt:
                rt.revogado = True
                if substituido_por:
                    rt.substituido_por = substituido_por
                s.commit()

    def revogar_todos_refresh(self, usuario_id: int) -> None:
        with self._sf() as s:
            s.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update())
            for rt in s.scalars(select(RefreshToken).where(RefreshToken.usuario_id == usuario_id, RefreshToken.revogado.is_(False))):
                rt.revogado = True
            s.commit()

    # =========================================================================
    # Auditoria / rate limit
    # =========================================================================

    def registrar_sessao_mfa(
        self, *, tipo: str, sucesso: bool, usuario_id: Optional[int] = None, referencia: Optional[str] = None,
        ip: Optional[str] = None, detalhe: Optional[dict] = None,
    ) -> bool:
        with self._sf() as s:
            s.add(SessaoMfa(usuario_id=usuario_id, referencia=referencia, tipo=tipo, sucesso=sucesso, ip=ip,
                            detalhe=detalhe, criado_em=tempo.agora()))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                if tipo == "mfa_usado" and sucesso:
                    return False
                raise
            return True

    def contar_eventos(
        self, *, tipo: str, desde: datetime, sucesso: Optional[bool] = False, usuario_id: Optional[int] = None,
        referencia: Optional[str] = None, ip: Optional[str] = None,
    ) -> int:
        with self._sf() as s:
            stmt = select(func.count(SessaoMfa.id)).where(SessaoMfa.tipo == tipo, SessaoMfa.criado_em >= desde)
            if sucesso is not None:
                stmt = stmt.where(SessaoMfa.sucesso.is_(sucesso))
            if usuario_id is not None:
                stmt = stmt.where(SessaoMfa.usuario_id == usuario_id)
            if referencia is not None:
                stmt = stmt.where(SessaoMfa.referencia == referencia)
            if ip is not None:
                stmt = stmt.where(SessaoMfa.ip == ip)
            return int(s.scalar(stmt) or 0)

    def registrar_log(self, *, ator: str, acao: str, ip: Optional[str] = None, detalhe: Optional[dict] = None,
                      usuario_id: Optional[int] = None, empresa_id: Optional[int] = None) -> None:
        """Trilha de auditoria (tabela) + evento no log estruturado. Falha ao gravar a
        trilha NÃO derruba a operação que já aconteceu (ex.: um Pix já debitado): vira
        erro no log, com o request_id, para alguém reconciliar."""
        from app.core import logs

        logs.evento(acao, usuario_id=usuario_id, empresa_id=empresa_id, ip=ip)
        try:
            with self._sf() as s:
                s.add(LogAuditoria(ator=ator, acao=acao, ip=ip, detalhe=detalhe, usuario_id=usuario_id,
                                   empresa_id=empresa_id, criado_em=tempo.agora()))
                s.commit()
        except Exception:  # noqa: BLE001
            logs.auditoria.exception("falha ao gravar trilha de auditoria", extra={"evento": acao})

    # =========================================================================
    # Conversões para dict
    # =========================================================================

    @staticmethod
    def _conta_dict(s: Session, c: Carteira) -> dict:
        nome = documento = None
        regime = None
        if c.titular_tipo == TipoPessoa.PF and c.usuario_id:
            u = s.get(Usuario, c.usuario_id)
            nome, documento = u.nome, u.cpf
        elif c.titular_tipo == TipoPessoa.PJ and c.empresa_id:
            e = s.get(Empresa, c.empresa_id)
            nome, documento, regime = (e.nome_fantasia or e.razao_social), e.cnpj, e.regime_apuracao.value
        else:
            nome = f"Astro {c.sistema}"
        return {
            "carteira_id": c.id,
            "agencia": c.agencia,
            "numero": c.numero,
            "titular_tipo": c.titular_tipo.value,
            "sistema": c.sistema,
            "usuario_id": c.usuario_id,
            "empresa_id": c.empresa_id,
            "nome": nome,
            "documento": documento,
            "regime_apuracao": regime,
            "saldo": c.saldo,
            "saldo_bloqueado": c.saldo_bloqueado,
        }

    @staticmethod
    def _usuario_auth_dict(u: Usuario) -> dict:
        return {
            "id": u.id, "nome": u.nome, "email": u.email, "cpf": u.cpf, "senha_hash": u.senha_hash,
            "papel": u.papel.value, "ativo": u.ativo, "tem_biometria": u.embedding_facial_cifrado is not None,
            "pontos": u.pontos, "data_nascimento": u.data_nascimento, "celular": u.celular,
            "kyc_status": u.kyc_status,
        }

    @staticmethod
    def _empresa_dict(e: Empresa) -> dict:
        return {
            "id": e.id, "cnpj": e.cnpj, "razao_social": e.razao_social, "nome_fantasia": e.nome_fantasia,
            "porte": e.porte, "regime_apuracao": e.regime_apuracao.value, "cnae": e.cnae, "setor": e.setor,
            "situacao_cadastral": e.situacao_cadastral, "verificada_por": e.verificada_por,
            "representante_usuario_id": e.representante_usuario_id, "kyb_status": e.kyb_status,
        }

    @staticmethod
    def _vinculo_dict(v: Vinculo) -> dict:
        return {
            "id": v.id, "usuario_id": v.usuario_id, "empresa_id": v.empresa_id, "papel": v.papel.value,
            "alcada": v.alcada, "alcada_diaria": v.alcada_diaria, "ativo": v.ativo, "status": v.status,
            "nome": v.usuario.nome if v.usuario else v.nome,
            "email": v.usuario.email if v.usuario else v.email,
            "cpf": v.cpf or (v.usuario.cpf if v.usuario else None), "celular": v.celular, "cargo": v.cargo,
            "criado_por_usuario_id": v.criado_por_usuario_id, "aceito_em": _utc(v.aceito_em),
            "status_em": _utc(v.status_em), "ultimo_acesso_em": _utc(v.ultimo_acesso_em),
            "criado_em": _utc(v.criado_em),
        }

    @staticmethod
    def _limite_dict(l: Limite) -> dict:
        return {
            "por_transacao": l.por_transacao, "diurno": l.diurno, "noturno": l.noturno,
            "pendente": None if l.pendente_vigente_em is None else {
                "por_transacao": l.pendente_por_transacao, "diurno": l.pendente_diurno,
                "noturno": l.pendente_noturno, "vigente_em": _utc(l.pendente_vigente_em),
            },
        }

    @staticmethod
    def _dispositivo_dict(d: Dispositivo) -> dict:
        return {"id": d.id, "nome": d.nome, "confiavel": d.confiavel and not d.bloqueado,
                "confiavel_em": _utc(d.confiavel_em), "bloqueado": d.bloqueado, "bloqueado_em": _utc(d.bloqueado_em),
                "ultimo_uso": _utc(d.ultimo_uso), "criado_em": _utc(d.criado_em),
                "atestacao": d.atestacao, "atestacao_em": _utc(d.atestacao_em)}

    def _transacao_dict(self, s: Session, t: Transacao) -> dict:
        origem = s.get(Carteira, t.origem_carteira_id)
        destino = s.get(Carteira, t.destino_carteira_id)
        o, d = self._conta_dict(s, origem), self._conta_dict(s, destino)
        return {
            "id": t.id,
            "tipo": t.tipo,
            "origem": {"carteira_id": o["carteira_id"], "agencia": o["agencia"], "numero": o["numero"], "nome": o["nome"]},
            "destino": {"carteira_id": d["carteira_id"], "agencia": d["agencia"], "numero": d["numero"], "nome": d["nome"]},
            "valor_bruto": t.valor_bruto,
            "cbs": t.cbs,
            "ibs": t.ibs,
            "liquido": t.liquido,
            "imposto_total": t.cbs + t.ibs,
            "tipo_destino": t.tipo_destino.value,
            "aplicou_split": t.aplicou_split,
            "auth_metodo": t.auth_metodo.value,
            "status": t.status.value,
            "bloqueio_ate": _utc(t.bloqueio_ate),
            "descricao": t.descricao,
            "verificacao_facial": t.verificacao_facial,
            "transacao_original_id": t.transacao_original_id,
            "data_hora": _utc(t.criado_em) or tempo.agora(),
        }

    def _cobranca_dict(self, s: Session, c: Cobranca) -> dict:
        rec = s.get(Carteira, c.recebedor_carteira_id)
        conta = self._conta_dict(s, rec)
        return {
            "id": c.id, "txid": c.txid, "valor": c.valor, "descricao": c.descricao, "vencimento": c.vencimento,
            "pagador_documento": c.pagador_documento, "nfe_chave": c.nfe_chave, "cbs": c.cbs, "ibs": c.ibs,
            "linha_digitavel": c.linha_digitavel, "status": c.status, "grupo_parcelamento": c.grupo_parcelamento,
            "parcela_numero": c.parcela_numero, "parcelas_total": c.parcelas_total, "autorizacao_id": c.autorizacao_id,
            "transacao_id": c.transacao_id, "paga_em": _utc(c.paga_em),
            "recebedor": {"carteira_id": rec.id, "nome": conta["nome"], "documento": conta["documento"],
                          "empresa_id": rec.empresa_id, "regime_apuracao": conta["regime_apuracao"]},
        }

    def _autorizacao_dict(self, s: Session, a: AutorizacaoRecorrente) -> dict:
        rec = self._conta_dict(s, s.get(Carteira, a.recebedor_carteira_id))
        pag = self._conta_dict(s, s.get(Carteira, a.pagador_carteira_id))
        return {
            "id": a.id, "descricao": a.descricao, "valor_maximo": a.valor_maximo, "periodicidade": a.periodicidade,
            "status": a.status, "aceita_em": _utc(a.aceita_em), "cancelada_em": _utc(a.cancelada_em),
            "recebedor": {"carteira_id": rec["carteira_id"], "nome": rec["nome"]},
            "pagador": {"carteira_id": pag["carteira_id"], "nome": pag["nome"]},
        }

    @staticmethod
    def _pendente_dict(p: OperacaoPendente) -> dict:
        return {
            "id": p.id, "empresa_id": p.empresa_id, "tipo": p.tipo, "valor": p.valor, "payload": p.payload,
            "descricao": p.descricao, "criado_por_usuario_id": p.criado_por_usuario_id, "status": p.status,
            "aprovacoes_necessarias": p.aprovacoes_necessarias or 1, "aprovacoes": list(p.aprovacoes or []),
            "decidido_por_usuario_id": p.decidido_por_usuario_id, "decidido_em": _utc(p.decidido_em),
            "resultado": p.resultado, "criado_em": _utc(p.criado_em),
        }

    @staticmethod
    def _contestacao_dict(c: Contestacao) -> dict:
        return {
            "id": c.id, "transacao_id": c.transacao_id, "aberta_por_usuario_id": c.aberta_por_usuario_id,
            "motivo": c.motivo, "status": c.status, "valor_devolvido": c.valor_devolvido,
            "decidida_em": _utc(c.decidida_em), "criado_em": _utc(c.criado_em),
        }

    @staticmethod
    def _webhook_dict(w: Webhook) -> dict:
        return {"id": w.id, "empresa_id": w.empresa_id, "url": w.url, "eventos": w.eventos, "ativo": w.ativo}

    @staticmethod
    def _entrega_dict(e: WebhookEntrega) -> dict:
        return {"id": e.id, "webhook_id": e.webhook_id, "evento": e.evento, "payload": e.payload, "status": e.status,
                "tentativas": e.tentativas, "ultima_resposta": e.ultima_resposta}
