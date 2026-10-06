"""
Repositório único do PayFlow (SQLAlchemy). Roda igual sobre Postgres (produção) e
SQLite (dev/testes) -- ver app/db/base.py. Toda a persistência passa por aqui;
services e routers nunca tocam a sessão/ORM direto.

Pontos sensíveis concentrados neste arquivo:
- `executar_transferencia`: débito + crédito + repasse do imposto à conta Governo
  + registro da transação + pernas do split + histórico de saldo -- tudo numa
  transação de banco só, com SELECT ... FOR UPDATE nas carteiras envolvidas
  (fecha a condição de corrida; no Postgres é efetivo, no SQLite o lock de banco
  serializa as escritas).
- Idempotência: `idempotency_key` única por transação -- um retry/double-click
  com a mesma chave devolve a transação já criada, sem duplicar (item #11).
- Refresh tokens: guardados só por hash, com rotação/revogação.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import usando_postgres
from app.db.models import (
    AuthMetodo,
    Carteira,
    HistoricoSaldo,
    LogAuditoria,
    Papel,
    RefreshToken,
    SessaoMfa,
    SplitLiquidacao,
    SplitRegra,
    TipoPessoa,
    Transacao,
    Usuario,
)
from app.repositories.exceptions import (
    CarteiraGovernoAusenteError,
    DocumentoDuplicadoError,
    EmailDuplicadoError,
    IdDuplicadoError,
    SaldoInsuficienteError,
)
from app.services.split_service import ResultadoSplit, ALIQUOTAS


class Repositorio:
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    # ===================== Contas / Usuários =====================

    def criar_conta(
        self,
        *,
        carteira_id: int,
        nome: str,
        email: str,
        senha_hash: str,
        tipo: TipoPessoa,
        documento: Optional[str],
        embedding_cifrado: Optional[bytes],
        papel: Papel = Papel.USUARIO,
        saldo_inicial: Decimal = Decimal("0.00"),
    ) -> dict:
        """Cria Usuario + Carteira numa única transação (fecha o item #10:
        atomicidade cadastro+biometria -- antes eram 2 escritas separadas)."""
        with self._sf() as s:
            usuario = Usuario(
                nome=nome,
                email=email.lower().strip(),
                senha_hash=senha_hash,
                tipo=tipo,
                documento=documento,
                papel=papel,
                embedding_facial_cifrado=embedding_cifrado,
            )
            carteira = Carteira(chave=str(carteira_id), saldo=saldo_inicial, usuario=usuario)
            s.add_all([usuario, carteira])
            try:
                s.flush()
            except IntegrityError as e:
                s.rollback()
                raise self._traduzir_integridade(e, carteira_id, email, documento)
            if saldo_inicial > 0:
                s.add(
                    HistoricoSaldo(
                        carteira_id=carteira.id,
                        saldo_anterior=Decimal("0.00"),
                        saldo_novo=saldo_inicial,
                        motivo="saldo_inicial",
                    )
                )
            s.commit()
            s.refresh(usuario)
            s.refresh(carteira)
            return self._conta_dict(usuario, carteira)

    @staticmethod
    def _traduzir_integridade(erro: IntegrityError, carteira_id: int, email: str, documento):
        texto = str(erro.orig).lower()
        if "chave" in texto or "carteira" in texto:
            return IdDuplicadoError(f"Já existe uma carteira com o ID {carteira_id}.")
        if "email" in texto:
            return EmailDuplicadoError("Já existe uma conta com esse e-mail.")
        if "documento" in texto:
            return DocumentoDuplicadoError("Já existe uma conta com esse documento.")
        # Fallback: não sabemos qual constraint -- devolve o mais provável no cadastro.
        return IdDuplicadoError(f"Já existe uma carteira com o ID {carteira_id}.")

    def obter_usuario_por_email(self, email: str) -> Optional[dict]:
        with self._sf() as s:
            u = s.scalar(select(Usuario).where(Usuario.email == email.lower().strip()))
            if not u:
                return None
            return self._usuario_auth_dict(u)

    def obter_usuario_por_id(self, usuario_id: int) -> Optional[dict]:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            return self._usuario_auth_dict(u) if u else None

    def obter_conta_por_carteira(self, carteira_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = self._buscar_carteira(s, carteira_id)
            return self._conta_dict(c.usuario, c) if c else None

    def carteira_existe(self, carteira_id: int) -> bool:
        with self._sf() as s:
            return self._buscar_carteira(s, carteira_id) is not None

    def listar_contas(self, *, limite: int = 50, offset: int = 0) -> list[dict]:
        with self._sf() as s:
            carteiras = s.scalars(
                select(Carteira).order_by(Carteira.id).limit(limite).offset(offset)
            ).all()
            return [self._conta_dict(c.usuario, c) for c in carteiras]

    def obter_carteira_do_usuario(self, usuario_id: int) -> Optional[dict]:
        with self._sf() as s:
            c = s.scalar(select(Carteira).where(Carteira.usuario_id == usuario_id))
            return self._conta_dict(c.usuario, c) if c else None

    # ---- Biometria ----

    def salvar_embedding_cifrado(self, carteira_id: int, blob: bytes) -> None:
        with self._sf() as s:
            c = self._buscar_carteira(s, carteira_id)
            c.usuario.embedding_facial_cifrado = blob
            s.commit()

    def obter_embedding_cifrado(self, carteira_id: int) -> Optional[bytes]:
        with self._sf() as s:
            c = self._buscar_carteira(s, carteira_id)
            if c is None or c.usuario.embedding_facial_cifrado is None:
                return None
            return bytes(c.usuario.embedding_facial_cifrado)

    # ===================== Conta Governo =====================

    def garantir_conta_governo(
        self, *, carteira_id: int, nome: str, email: str, senha_hash: str, documento: str
    ) -> dict:
        """Cria a conta GOV se ainda não existir (idempotente). É o destino do
        imposto retido no split."""
        with self._sf() as s:
            gov = s.scalar(select(Usuario).where(Usuario.tipo == TipoPessoa.GOV))
            if gov:
                c = gov.carteiras[0] if gov.carteiras else None
                return self._conta_dict(gov, c)
        return self.criar_conta(
            carteira_id=carteira_id,
            nome=nome,
            email=email,
            senha_hash=senha_hash,
            tipo=TipoPessoa.GOV,
            documento=documento,
            embedding_cifrado=None,
            papel=Papel.ADMIN,
        )

    def _carteira_governo(self, s) -> Carteira:
        gov = s.scalar(select(Usuario).where(Usuario.tipo == TipoPessoa.GOV))
        if not gov or not gov.carteiras:
            raise CarteiraGovernoAusenteError()
        return gov.carteiras[0]

    # ===================== Transferência + Split =====================

    def executar_transferencia(
        self,
        *,
        origem_carteira_id: int,
        destino_carteira_id: int,
        split: ResultadoSplit,
        verificacao_facial: Optional[dict],
        auth_metodo: AuthMetodo,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        with self._sf() as s:
            # Idempotência: se a chave já produziu uma transação, devolve ela.
            if idempotency_key:
                ja = s.scalar(
                    select(Transacao).where(Transacao.idempotency_key == idempotency_key)
                )
                if ja:
                    return self._transacao_dict(s, ja)

            # Trava as carteiras envolvidas (origem, destino e GOV se houver imposto),
            # sempre na mesma ordem (por chave) pra não dar deadlock entre A->B e B->A.
            chaves = {str(origem_carteira_id), str(destino_carteira_id)}
            gov_carteira = None
            if split.aplicou_split and (split.cbs + split.ibs) > 0:
                gov_carteira = self._carteira_governo(s)
                chaves.add(gov_carteira.chave)

            stmt = select(Carteira).where(Carteira.chave.in_(sorted(chaves)))
            if usando_postgres():
                stmt = stmt.with_for_update()
            carteiras = {c.chave: c for c in s.scalars(stmt).all()}

            origem = carteiras[str(origem_carteira_id)]
            destino = carteiras[str(destino_carteira_id)]
            gov = carteiras.get(gov_carteira.chave) if gov_carteira else None

            if origem.saldo < split.valor_bruto:
                raise SaldoInsuficienteError()

            # Débito integral da origem; destino recebe só o líquido; GOV recebe imposto.
            self._mover(s, origem, -split.valor_bruto, motivo="transferencia")
            self._mover(s, destino, split.liquido, motivo="transferencia")
            imposto = split.cbs + split.ibs
            if gov is not None and imposto > 0:
                self._mover(s, gov, imposto, motivo="imposto")

            transacao = Transacao(
                origem_carteira_id=origem.id,
                destino_carteira_id=destino.id,
                valor_bruto=split.valor_bruto,
                cbs=split.cbs,
                ibs=split.ibs,
                liquido=split.liquido,
                tipo_destino=destino.usuario.tipo,
                aplicou_split=split.aplicou_split,
                auth_metodo=auth_metodo,
                verificacao_facial=verificacao_facial,
                idempotency_key=idempotency_key,
            )
            s.add(transacao)
            s.flush()

            # Pernas do split (reconstituição fiscal).
            s.add(
                SplitLiquidacao(
                    transacao_id=transacao.id,
                    natureza="LIQUIDO",
                    carteira_destino_id=destino.id,
                    valor=split.liquido,
                )
            )
            if gov is not None and imposto > 0:
                if split.cbs > 0:
                    s.add(SplitLiquidacao(transacao_id=transacao.id, natureza="CBS", carteira_destino_id=gov.id, valor=split.cbs))
                if split.ibs > 0:
                    s.add(SplitLiquidacao(transacao_id=transacao.id, natureza="IBS", carteira_destino_id=gov.id, valor=split.ibs))

            # Liga os HistoricoSaldo recém-criados (motivo transferencia/imposto) a esta transação.
            self._vincular_historico(s, transacao.id)

            try:
                s.commit()
            except IntegrityError:
                # Corrida na idempotency_key: outra requisição idêntica ganhou.
                s.rollback()
                if idempotency_key:
                    ja = s.scalar(select(Transacao).where(Transacao.idempotency_key == idempotency_key))
                    if ja:
                        return self._transacao_dict(s, ja)
                raise
            s.refresh(transacao)
            return self._transacao_dict(s, transacao)

    def depositar(self, *, carteira_id: int, valor: Decimal) -> dict:
        """Depósito controlado: a conta Governo (emissor) credita a carteira.
        Sem split (depósito não é fato gerador de imposto). Debita a GOV (o
        emissor pode ficar negativo -- representa dinheiro emitido em circulação)."""
        with self._sf() as s:
            gov_carteira = self._carteira_governo(s)
            chaves = sorted({str(carteira_id), gov_carteira.chave})
            stmt = select(Carteira).where(Carteira.chave.in_(chaves))
            if usando_postgres():
                stmt = stmt.with_for_update()
            carteiras = {c.chave: c for c in s.scalars(stmt).all()}
            destino = carteiras[str(carteira_id)]
            gov = carteiras[gov_carteira.chave]

            self._mover(s, gov, -valor, motivo="emissao")
            self._mover(s, destino, valor, motivo="deposito")

            transacao = Transacao(
                origem_carteira_id=gov.id,
                destino_carteira_id=destino.id,
                valor_bruto=valor,
                cbs=Decimal("0.00"),
                ibs=Decimal("0.00"),
                liquido=valor,
                tipo_destino=destino.usuario.tipo,
                aplicou_split=False,
                auth_metodo=AuthMetodo.SENHA,
            )
            s.add(transacao)
            s.flush()
            self._vincular_historico(s, transacao.id)
            s.commit()
            s.refresh(transacao)
            return self._transacao_dict(s, transacao)

    def _mover(self, s, carteira: Carteira, delta: Decimal, *, motivo: str) -> None:
        anterior = carteira.saldo
        carteira.saldo = anterior + delta
        s.add(
            HistoricoSaldo(
                carteira_id=carteira.id,
                saldo_anterior=anterior,
                saldo_novo=carteira.saldo,
                motivo=motivo,
            )
        )

    @staticmethod
    def _vincular_historico(s, transacao_id: int) -> None:
        # Os HistoricoSaldo criados nesta sessão ainda sem transacao_id são desta transferência.
        for obj in s.new:
            if isinstance(obj, HistoricoSaldo) and obj.transacao_id is None:
                obj.transacao_id = transacao_id

    def listar_transacoes(
        self, *, carteira_id: Optional[int] = None, limite: int = 50, offset: int = 0
    ) -> list[dict]:
        with self._sf() as s:
            stmt = select(Transacao)
            if carteira_id is not None:
                c = self._buscar_carteira(s, carteira_id)
                if c is None:
                    return []
                stmt = stmt.where(
                    (Transacao.origem_carteira_id == c.id)
                    | (Transacao.destino_carteira_id == c.id)
                )
            stmt = stmt.order_by(Transacao.id.desc()).limit(limite).offset(offset)
            return [self._transacao_dict(s, t) for t in s.scalars(stmt).all()]

    def total_retido_governo(self) -> dict:
        with self._sf() as s:
            cbs = s.scalar(select(func.coalesce(func.sum(Transacao.cbs), 0))) or Decimal("0")
            ibs = s.scalar(select(func.coalesce(func.sum(Transacao.ibs), 0))) or Decimal("0")
            n = s.scalar(select(func.count(Transacao.id)).where(Transacao.aplicou_split.is_(True))) or 0
            return {
                "cbs_total": Decimal(cbs),
                "ibs_total": Decimal(ibs),
                "total": Decimal(cbs) + Decimal(ibs),
                "transacoes_com_split": int(n),
            }

    # ===================== Refresh tokens =====================

    def salvar_refresh(self, *, usuario_id: int, jti: str, token_hash: str, expira_em: datetime) -> None:
        with self._sf() as s:
            s.add(RefreshToken(usuario_id=usuario_id, jti=jti, token_hash=token_hash, expira_em=expira_em))
            s.commit()

    def obter_refresh(self, token_hash: str) -> Optional[dict]:
        with self._sf() as s:
            rt = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            if not rt:
                return None
            return {
                "id": rt.id,
                "usuario_id": rt.usuario_id,
                "jti": rt.jti,
                "revogado": rt.revogado,
                "expira_em": rt.expira_em,
                "substituido_por": rt.substituido_por,
            }

    def revogar_refresh(self, jti: str, substituido_por: Optional[str] = None) -> None:
        with self._sf() as s:
            rt = s.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
            if rt:
                rt.revogado = True
                if substituido_por:
                    rt.substituido_por = substituido_por
                s.commit()

    def revogar_todos_refresh(self, usuario_id: int) -> None:
        """Usado na detecção de reuso (possível roubo) e no logout de todos os
        dispositivos."""
        with self._sf() as s:
            for rt in s.scalars(select(RefreshToken).where(RefreshToken.usuario_id == usuario_id, RefreshToken.revogado.is_(False))):
                rt.revogado = True
            s.commit()

    # ===================== Auditoria / rate-limit =====================

    def registrar_sessao_mfa(
        self,
        *,
        tipo: str,
        sucesso: bool,
        usuario_id: Optional[int] = None,
        referencia: Optional[str] = None,
        ip: Optional[str] = None,
        detalhe: Optional[dict] = None,
    ) -> None:
        with self._sf() as s:
            s.add(
                SessaoMfa(
                    usuario_id=usuario_id,
                    referencia=referencia,
                    tipo=tipo,
                    sucesso=sucesso,
                    ip=ip,
                    detalhe=detalhe,
                )
            )
            s.commit()

    def contar_falhas_recentes(
        self, *, tipo: str, desde: datetime, usuario_id: Optional[int] = None, referencia: Optional[str] = None
    ) -> int:
        with self._sf() as s:
            stmt = select(func.count(SessaoMfa.id)).where(
                SessaoMfa.tipo == tipo,
                SessaoMfa.sucesso.is_(False),
                SessaoMfa.criado_em >= desde,
            )
            if usuario_id is not None:
                stmt = stmt.where(SessaoMfa.usuario_id == usuario_id)
            if referencia is not None:
                stmt = stmt.where(SessaoMfa.referencia == referencia)
            return int(s.scalar(stmt) or 0)

    def registrar_log(self, *, ator: str, acao: str, ip: Optional[str] = None, detalhe: Optional[dict] = None) -> None:
        with self._sf() as s:
            s.add(LogAuditoria(ator=ator, acao=acao, ip=ip, detalhe=detalhe))
            s.commit()

    # ===================== Split regras (seed) =====================

    def seed_split_regras(self) -> None:
        with self._sf() as s:
            for vig, dados in ALIQUOTAS.items():
                existe = s.scalar(select(SplitRegra).where(SplitRegra.vigencia == vig))
                if not existe:
                    s.add(
                        SplitRegra(
                            vigencia=vig,
                            descricao=str(dados.get("descricao", "")),
                            aliquota_cbs=dados["cbs"],
                            aliquota_ibs=dados["ibs"],
                        )
                    )
            s.commit()

    # ===================== Helpers =====================

    @staticmethod
    def _buscar_carteira(s, carteira_id: int) -> Optional[Carteira]:
        return s.scalar(select(Carteira).where(Carteira.chave == str(carteira_id)))

    @staticmethod
    def _conta_dict(usuario: Usuario, carteira: Optional[Carteira]) -> dict:
        return {
            "usuario_id": usuario.id,
            "carteira_id": int(carteira.chave) if carteira else None,
            "nome": usuario.nome,
            "email": usuario.email,
            "tipo": usuario.tipo.value,
            "documento": usuario.documento,
            "papel": usuario.papel.value,
            "saldo": carteira.saldo if carteira else Decimal("0.00"),
            "tem_biometria": usuario.embedding_facial_cifrado is not None,
        }

    @staticmethod
    def _usuario_auth_dict(u: Usuario) -> dict:
        return {
            "id": u.id,
            "nome": u.nome,
            "email": u.email,
            "senha_hash": u.senha_hash,
            "papel": u.papel.value,
            "tipo": u.tipo.value,
            "ativo": u.ativo,
        }

    def _transacao_dict(self, s, t: Transacao) -> dict:
        origem = s.get(Carteira, t.origem_carteira_id)
        destino = s.get(Carteira, t.destino_carteira_id)
        return {
            "id": t.id,
            "origem_carteira_id": int(origem.chave),
            "destino_carteira_id": int(destino.chave),
            "valor": t.valor_bruto,  # compat: "valor" == bruto
            "valor_bruto": t.valor_bruto,
            "cbs": t.cbs,
            "ibs": t.ibs,
            "liquido": t.liquido,
            "imposto_total": t.cbs + t.ibs,
            "tipo_destino": t.tipo_destino.value,
            "aplicou_split": t.aplicou_split,
            "auth_metodo": t.auth_metodo.value,
            "verificacao_facial": t.verificacao_facial,
            "idempotency_key": t.idempotency_key,
            "data_hora": t.criado_em or datetime.now(timezone.utc),
        }
