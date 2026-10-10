"""
Métodos do repositório para identidade, sessões, equipe PJ, folha e auditoria.

Ficam num mixin separado (o Repositorio herda dele) só para o repository.py não
crescer além do legível. Mesma regra de sempre: services e routers não tocam na
sessão/ORM; o que precisa ser atômico (aprovação dupla, aceite de convite) mora
aqui, com UPDATE condicional / SELECT ... FOR UPDATE.
"""

import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import tempo
from app.db.models import (
    CasoKyc,
    DocumentoEmpresa,
    DocumentoIdentidade,
    Dispositivo,
    Empresa,
    Funcionario,
    JtiDpop,
    LogAuditoria,
    OperacaoPendente,
    PapelVinculo,
    RefreshToken,
    Usuario,
    Vinculo,
)
from app.repositories.exceptions import CpfDuplicadoError

# Status que ocupam uma "vaga" de usuário da empresa (limite por porte).
STATUS_OCUPAM_VAGA = ("pendente", "aguardando", "ativo", "suspenso")


def _utc(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class RepositorioExtras:
    _sf = None  # definido pelo Repositorio

    # =========================================================================
    # Pessoas
    # =========================================================================

    def obter_usuario_por_cpf(self, cpf: str) -> Optional[dict]:
        with self._sf() as s:
            u = s.scalar(select(Usuario).where(Usuario.cpf == cpf))
            return self._usuario_auth_dict(u) if u else None

    def atualizar_senha_hash(self, usuario_id: int, senha_hash: str) -> None:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            if u:
                u.senha_hash = senha_hash
                s.commit()

    def atualizar_kyc_status(self, usuario_id: int, status: str) -> None:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            if u:
                u.kyc_status = status
                s.commit()

    def salvar_embedding(self, usuario_id: int, blob: bytes) -> None:
        with self._sf() as s:
            u = s.get(Usuario, usuario_id)
            if u:
                u.embedding_facial_cifrado = blob
                s.commit()

    # =========================================================================
    # Sessões (família de refresh tokens) e dispositivos
    # =========================================================================

    def sessao_ativa(self, sessao_id: str) -> bool:
        with self._sf() as s:
            n = s.scalar(
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.sessao_id == sessao_id, RefreshToken.revogado.is_(False),
                    RefreshToken.expira_em > tempo.agora(),
                )
            )
            return bool(n)

    def listar_sessoes(self, usuario_id: int) -> list[dict]:
        """Uma linha por sessão ativa, com o aparelho e o último uso (o refresh
        mais recente da família)."""
        with self._sf() as s:
            rts = s.scalars(
                select(RefreshToken).where(
                    RefreshToken.usuario_id == usuario_id, RefreshToken.revogado.is_(False),
                    RefreshToken.expira_em > tempo.agora(), RefreshToken.sessao_id.is_not(None),
                ).order_by(RefreshToken.id.desc())
            ).all()
            vistas: dict[str, dict] = {}
            for rt in rts:
                if rt.sessao_id in vistas:
                    continue
                disp = s.get(Dispositivo, rt.dispositivo_id) if rt.dispositivo_id else None
                vistas[rt.sessao_id] = {
                    "sessao_id": rt.sessao_id, "ip": rt.ip, "user_agent": rt.user_agent,
                    "ultimo_uso": _utc(rt.criado_em), "expira_em": _utc(rt.expira_em),
                    "dispositivo": {"id": disp.id, "nome": disp.nome, "confiavel": disp.confiavel and not disp.bloqueado}
                    if disp else None,
                }
            return list(vistas.values())

    def revogar_sessao(self, usuario_id: int, sessao_id: str) -> bool:
        with self._sf() as s:
            n = s.query(RefreshToken).filter(
                RefreshToken.usuario_id == usuario_id, RefreshToken.sessao_id == sessao_id,
                RefreshToken.revogado.is_(False),
            ).update({"revogado": True})
            s.commit()
            return n > 0

    def revogar_outras_sessoes(self, usuario_id: int, manter: Optional[str]) -> int:
        with self._sf() as s:
            q = s.query(RefreshToken).filter(RefreshToken.usuario_id == usuario_id, RefreshToken.revogado.is_(False))
            if manter:
                q = q.filter((RefreshToken.sessao_id != manter) | RefreshToken.sessao_id.is_(None))
            n = q.update({"revogado": True}, synchronize_session=False)
            s.commit()
            return n

    def revogar_sessoes_do_dispositivo(self, usuario_id: int, dispositivo_id: int) -> int:
        with self._sf() as s:
            n = s.query(RefreshToken).filter(
                RefreshToken.usuario_id == usuario_id, RefreshToken.dispositivo_id == dispositivo_id,
                RefreshToken.revogado.is_(False),
            ).update({"revogado": True})
            s.commit()
            return n

    def bloquear_dispositivo(self, usuario_id: int, dispositivo_id: int) -> Optional[dict]:
        with self._sf() as s:
            d = s.get(Dispositivo, dispositivo_id)
            if not d or d.usuario_id != usuario_id:
                return None
            d.bloqueado, d.bloqueado_em, d.confiavel = True, tempo.agora(), False
            s.commit()
            s.refresh(d)
            return self._dispositivo_dict(d)

    def desbloquear_dispositivo(self, usuario_id: int, dispositivo_id: int) -> Optional[dict]:
        with self._sf() as s:
            d = s.get(Dispositivo, dispositivo_id)
            if not d or d.usuario_id != usuario_id:
                return None
            d.bloqueado, d.bloqueado_em = False, None
            s.commit()
            s.refresh(d)
            return self._dispositivo_dict(d)

    def dispositivo_por_id(self, dispositivo_id: int) -> Optional[dict]:
        """Inclui o id_hash -- só para checagens internas (nunca vai para a API)."""
        with self._sf() as s:
            d = s.get(Dispositivo, dispositivo_id)
            if not d:
                return None
            return {**self._dispositivo_dict(d), "usuario_id": d.usuario_id, "id_hash": d.id_hash}

    def dispositivo_bloqueado(self, usuario_id: int, id_hash: str) -> bool:
        with self._sf() as s:
            d = s.scalar(select(Dispositivo).where(Dispositivo.usuario_id == usuario_id, Dispositivo.id_hash == id_hash))
            return bool(d and d.bloqueado)

    # =========================================================================
    # KYC / KYB
    # =========================================================================

    def criar_caso_kyc(self, *, tipo: str, status: str, nivel_risco: str, motivos: list,
                       usuario_id: Optional[int] = None, empresa_id: Optional[int] = None) -> dict:
        with self._sf() as s:
            c = CasoKyc(usuario_id=usuario_id, empresa_id=empresa_id, tipo=tipo, status=status, nivel_risco=nivel_risco,
                        motivos=motivos, criado_em=tempo.agora(),
                        concluido_em=tempo.agora() if status in ("aprovado", "reprovado") else None)
            s.add(c)
            s.commit()
            return self._caso_dict(s, c)

    def vincular_caso_kyc(self, caso_id: int, *, usuario_id: Optional[int] = None, empresa_id: Optional[int] = None) -> None:
        with self._sf() as s:
            c = s.get(CasoKyc, caso_id)
            if c:
                if usuario_id is not None:
                    c.usuario_id = usuario_id
                if empresa_id is not None:
                    c.empresa_id = empresa_id
                s.commit()

    def registrar_documento_identidade(self, *, caso_id: int, tipo: str, status: str, provedor: str, sha256: str,
                                       campos: dict, verificacoes: dict) -> dict:
        with self._sf() as s:
            d = DocumentoIdentidade(caso_id=caso_id, tipo=tipo, status=status, provedor=provedor, sha256=sha256,
                                    campos=campos, verificacoes=verificacoes, criado_em=tempo.agora())
            s.add(d)
            s.commit()
            return {"id": d.id, "tipo": d.tipo, "status": d.status, "provedor": d.provedor, "campos": d.campos,
                    "verificacoes": d.verificacoes, "criado_em": _utc(d.criado_em)}

    def ultimo_caso_kyc(self, *, usuario_id: Optional[int] = None, empresa_id: Optional[int] = None) -> Optional[dict]:
        with self._sf() as s:
            stmt = select(CasoKyc)
            stmt = stmt.where(CasoKyc.usuario_id == usuario_id) if usuario_id is not None else stmt.where(CasoKyc.empresa_id == empresa_id)
            c = s.scalar(stmt.order_by(CasoKyc.id.desc()).limit(1))
            return self._caso_dict(s, c) if c else None

    def _caso_dict(self, s, c: CasoKyc) -> dict:
        docs = s.scalars(select(DocumentoIdentidade).where(DocumentoIdentidade.caso_id == c.id)).all()
        return {
            "id": c.id, "tipo": c.tipo, "status": c.status, "nivel_risco": c.nivel_risco, "motivos": c.motivos or [],
            "criado_em": _utc(c.criado_em), "concluido_em": _utc(c.concluido_em),
            "documentos": [{"id": d.id, "tipo": d.tipo, "status": d.status, "provedor": d.provedor,
                            "campos": d.campos, "verificacoes": d.verificacoes} for d in docs],
        }

    def listar_casos_kyc(self, status: str = "em_analise", limite: int = 100) -> list[dict]:
        with self._sf() as s:
            cs = s.scalars(select(CasoKyc).where(CasoKyc.status == status).order_by(CasoKyc.id).limit(limite)).all()
            res = []
            for c in cs:
                u = s.get(Usuario, c.usuario_id) if c.usuario_id else None
                res.append({**self._caso_dict(s, c), "usuario": {"id": u.id, "nome": u.nome, "email": u.email}
                            if u else None})
            return res

    def decidir_caso_kyc(self, caso_id: int, status: str) -> Optional[dict]:
        """Análise humana: em_analise -> aprovado | reprovado. Atualiza a pessoa."""
        with self._sf() as s:
            c = s.get(CasoKyc, caso_id)
            if c is None or c.status != "em_analise":
                return None
            c.status, c.concluido_em = status, tempo.agora()
            if c.usuario_id:
                u = s.get(Usuario, c.usuario_id)
                if u:
                    u.kyc_status = status
            s.commit()
            return self._caso_dict(s, c)

    def registrar_documento_empresa(self, *, empresa_id: int, tipo: str, mime: str, tamanho: int, sha256: str,
                                    status: str, verificacoes: dict, enviado_por: Optional[int]) -> dict:
        with self._sf() as s:
            d = DocumentoEmpresa(empresa_id=empresa_id, tipo=tipo, mime=mime, tamanho=tamanho, sha256=sha256,
                                 status=status, verificacoes=verificacoes, enviado_por_usuario_id=enviado_por,
                                 criado_em=tempo.agora())
            s.add(d)
            s.commit()
            return self._doc_empresa_dict(d)

    def listar_documentos_empresa(self, empresa_id: int) -> list[dict]:
        with self._sf() as s:
            ds = s.scalars(select(DocumentoEmpresa).where(DocumentoEmpresa.empresa_id == empresa_id)
                           .order_by(DocumentoEmpresa.id.desc())).all()
            return [self._doc_empresa_dict(d) for d in ds]

    @staticmethod
    def _doc_empresa_dict(d: DocumentoEmpresa) -> dict:
        return {"id": d.id, "tipo": d.tipo, "mime": d.mime, "tamanho": d.tamanho, "sha256": d.sha256,
                "status": d.status, "verificacoes": d.verificacoes, "criado_em": _utc(d.criado_em)}

    def atualizar_kyb_status(self, empresa_id: int, status: str) -> None:
        with self._sf() as s:
            e = s.get(Empresa, empresa_id)
            if e:
                e.kyb_status = status
                s.commit()

    # =========================================================================
    # Equipe (vínculos por convite)
    # =========================================================================

    def criar_convite(self, *, empresa_id: int, cpf: str, nome: str, email: Optional[str], celular: Optional[str],
                      cargo: Optional[str], papel: PapelVinculo, alcada: Optional[Decimal], status: str,
                      criado_por: int, alcada_diaria: Optional[Decimal] = None) -> dict:
        with self._sf() as s:
            agora = tempo.agora()
            v = Vinculo(empresa_id=empresa_id, cpf=cpf, nome=nome, email=(email or "").lower().strip() or None,
                        celular=celular, cargo=cargo, papel=papel, alcada=alcada, alcada_diaria=alcada_diaria,
                        status=status, ativo=False,
                        criado_por_usuario_id=criado_por, status_em=agora, criado_em=agora)
            s.add(v)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise CpfDuplicadoError("Esse CPF já tem acesso (ou convite) nesta empresa.") from None
            s.refresh(v)
            return self._vinculo_dict(v)

    def obter_vinculo_por_id(self, vinculo_id: int) -> Optional[dict]:
        with self._sf() as s:
            v = s.get(Vinculo, vinculo_id)
            return self._vinculo_dict(v) if v else None

    def atualizar_vinculo(self, vinculo_id: int, **campos) -> Optional[dict]:
        """Atualiza papel/alçada/status/etc. Mantém `ativo` == (status == ativo)."""
        with self._sf() as s:
            v = s.get(Vinculo, vinculo_id)
            if not v:
                return None
            for k, val in campos.items():
                setattr(v, k, val)
            if "status" in campos:
                v.ativo = campos["status"] == "ativo"
                v.status_em = tempo.agora()
            s.commit()
            s.refresh(v)
            return self._vinculo_dict(v)

    def convites_do_cpf(self, cpf: str) -> list[dict]:
        with self._sf() as s:
            vs = s.scalars(select(Vinculo).where(Vinculo.cpf == cpf, Vinculo.status == "pendente")
                           .order_by(Vinculo.id.desc())).all()
            res = []
            for v in vs:
                e = s.get(Empresa, v.empresa_id)
                quem = s.get(Usuario, v.criado_por_usuario_id) if v.criado_por_usuario_id else None
                res.append({**self._vinculo_dict(v),
                            "empresa": {"id": e.id, "nome": e.nome_fantasia or e.razao_social, "cnpj": e.cnpj,
                                        "porte": e.porte},
                            "convidado_por": quem.nome if quem else None})
            return res

    def aceitar_convite(self, vinculo_id: int, usuario_id: int, cpf: str) -> Optional[dict]:
        """pendente -> ativo, preso ao CPF do convite. UPDATE condicional: dois
        aceites simultâneos não passam."""
        with self._sf() as s:
            alvo = s.get(Vinculo, vinculo_id)
            if alvo is None:
                return None
            ja_tem = s.scalar(select(Vinculo.id).where(Vinculo.usuario_id == usuario_id,
                                                       Vinculo.empresa_id == alvo.empresa_id))
            if ja_tem:
                return None
            agora = tempo.agora()
            n = s.query(Vinculo).filter(
                Vinculo.id == vinculo_id, Vinculo.status == "pendente", Vinculo.cpf == cpf,
            ).update({"status": "ativo", "ativo": True, "usuario_id": usuario_id, "aceito_em": agora,
                      "status_em": agora}, synchronize_session=False)
            s.commit()
            if n != 1:
                return None
            # O UPDATE em massa não mexe no `alvo` já carregado (expire_on_commit=False): recarrega.
            return self._vinculo_dict(s.get(Vinculo, vinculo_id, populate_existing=True))

    def contar_vagas_ocupadas(self, empresa_id: int) -> int:
        with self._sf() as s:
            return int(s.scalar(select(func.count(Vinculo.id)).where(
                Vinculo.empresa_id == empresa_id, Vinculo.status.in_(STATUS_OCUPAM_VAGA))) or 0)

    def marcar_acesso_vinculo(self, vinculo_id: int) -> None:
        with self._sf() as s:
            v = s.get(Vinculo, vinculo_id)
            if v:
                v.ultimo_acesso_em = tempo.agora()
                s.commit()

    # =========================================================================
    # Aprovações (maker-checker com N aprovadores)
    # =========================================================================

    def registrar_aprovacao(self, pendente_id: int, usuario_id: int, nome: str) -> Optional[str]:
        """Soma uma aprovação. "completa" quando atinge o necessário (e já reserva a
        operação como aprovada), "parcial" se ainda falta, None se a operação não
        está mais pendente ou essa pessoa já aprovou. Linha travada (FOR UPDATE):
        dois aprovadores ao mesmo tempo não pulam a contagem."""
        with self._sf() as s:
            p = s.scalar(select(OperacaoPendente).where(OperacaoPendente.id == pendente_id).with_for_update())
            if p is None or p.status != "pendente":
                return None
            lista = list(p.aprovacoes or [])
            if any(a.get("usuario_id") == usuario_id for a in lista):
                return None
            lista.append({"usuario_id": usuario_id, "nome": nome, "em": tempo.agora().isoformat()})
            p.aprovacoes = lista
            if len(lista) >= (p.aprovacoes_necessarias or 1):
                p.status, p.decidido_por_usuario_id, p.decidido_em = "aprovada", usuario_id, tempo.agora()
                s.commit()
                return "completa"
            s.commit()
            return "parcial"

    # =========================================================================
    # Funcionários (folha)
    # =========================================================================

    def criar_funcionario(self, *, empresa_id: int, nome: str, cpf: str, cargo: Optional[str],
                          salario: Optional[Decimal], criado_por: int) -> dict:
        with self._sf() as s:
            f = s.scalar(select(Funcionario).where(Funcionario.empresa_id == empresa_id, Funcionario.cpf == cpf))
            if f is not None and f.ativo:
                raise CpfDuplicadoError("Esse CPF já está na folha desta empresa.")
            if f is None:
                f = Funcionario(empresa_id=empresa_id, cpf=cpf)
                s.add(f)
            f.nome, f.cargo, f.salario, f.ativo, f.desligado_em = nome, cargo, salario, True, None
            f.criado_por_usuario_id, f.criado_em = criado_por, tempo.agora()
            s.commit()
            s.refresh(f)
            return self._funcionario_dict(s, f)

    def listar_funcionarios(self, empresa_id: int, *, somente_ativos: bool = True) -> list[dict]:
        with self._sf() as s:
            stmt = select(Funcionario).where(Funcionario.empresa_id == empresa_id)
            if somente_ativos:
                stmt = stmt.where(Funcionario.ativo.is_(True))
            return [self._funcionario_dict(s, f) for f in s.scalars(stmt.order_by(Funcionario.nome)).all()]

    def obter_funcionario(self, funcionario_id: int) -> Optional[dict]:
        with self._sf() as s:
            f = s.get(Funcionario, funcionario_id)
            return self._funcionario_dict(s, f) if f else None

    def desligar_funcionario(self, empresa_id: int, funcionario_id: int) -> bool:
        with self._sf() as s:
            f = s.get(Funcionario, funcionario_id)
            if not f or f.empresa_id != empresa_id or not f.ativo:
                return False
            f.ativo, f.desligado_em = False, tempo.agora()
            s.commit()
            return True

    def contar_funcionarios_ativos(self, empresa_id: int) -> int:
        with self._sf() as s:
            return int(s.scalar(select(func.count(Funcionario.id)).where(
                Funcionario.empresa_id == empresa_id, Funcionario.ativo.is_(True))) or 0)

    def _funcionario_dict(self, s, f: Funcionario) -> dict:
        from app.db.models import Carteira  # evita ciclo de import no topo

        u = s.scalar(select(Usuario).where(Usuario.cpf == f.cpf))
        pf = s.scalar(select(Carteira).where(Carteira.usuario_id == u.id)) if u else None
        return {"id": f.id, "empresa_id": f.empresa_id, "nome": f.nome, "cpf": f.cpf, "cargo": f.cargo,
                "salario": f.salario, "ativo": f.ativo, "criado_em": _utc(f.criado_em),
                "desligado_em": _utc(f.desligado_em),
                # O destino do salário é SEMPRE a conta PF deste CPF -- informado aqui só para exibir.
                "conta_salario": {"carteira_id": pf.id, "agencia": pf.agencia, "numero": pf.numero} if pf else None}

    # =========================================================================
    # Auditoria
    # =========================================================================

    def listar_auditoria(self, *, empresa_id: Optional[int] = None, usuario_id: Optional[int] = None,
                         limite: int = 100) -> list[dict]:
        with self._sf() as s:
            stmt = select(LogAuditoria)
            if empresa_id is not None:
                stmt = stmt.where(LogAuditoria.empresa_id == empresa_id)
            if usuario_id is not None:
                stmt = stmt.where(LogAuditoria.usuario_id == usuario_id)
            logs = s.scalars(stmt.order_by(LogAuditoria.id.desc()).limit(min(limite, 500))).all()
            return [{"id": l.id, "ator": l.ator, "acao": l.acao, "usuario_id": l.usuario_id, "empresa_id": l.empresa_id,
                     "ip": l.ip, "detalhe": l.detalhe, "criado_em": _utc(l.criado_em)} for l in logs]

    # ------------------------------------------------------------------ DPoP

    def registrar_jti_dpop(self, jti: str, *, expira_em: datetime) -> bool:
        """True se o jti é novo (e fica guardado); False se já foi usado.
        A chave primária garante uso único mesmo com requisições simultâneas."""
        with self._sf() as s:
            if random.random() < 0.05:  # limpeza ocasional das vencidas
                s.query(JtiDpop).filter(JtiDpop.expira_em < tempo.agora()).delete(synchronize_session=False)
            s.add(JtiDpop(jti=jti, expira_em=expira_em))
            try:
                s.commit()
                return True
            except IntegrityError:
                s.rollback()
                return False
