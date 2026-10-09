"""
Política de acesso por PORTE da empresa (MEI, PME, Grande).

A regra de fundo é a mesma para todos: quem acessa a conta da empresa é sempre
uma PESSOA, com o próprio login, a própria biometria e um vínculo (papel +
alçada). Não existe "login da empresa", nem conta do representante compartilhada
com o contador -- cada um tem a sua. O que muda por porte é o RIGOR:

MEI -- dono único. Só o titular é administrador; pode dar acesso a quem trabalha
  com ele (o funcionário que a lei permite + quem ajuda, ex.: contador) apenas
  como operador ou consulta. Sem dupla aprovação (não há a quem pedir), mas toda
  saída acima do limite facial exige o rosto.

PME (ME/EPP) -- vários usuários e todos os papéis. Acima da alçada de quem lançou,
  outra pessoa aprova (maker-checker). Dar poder (admin/aprovador, alçada maior)
  exige o rosto de quem está dando.

GRANDE -- além do PME:
  * quatro olhos também na GESTÃO DE ACESSO: conceder admin/aprovador, aumentar
    alçada ou reativar alguém fica "aguardando" até OUTRO admin aprovar (se a
    empresa tiver ao menos 2 admins ativos);
  * operador SEMPRE com alçada definida (nunca "sem limite");
  * acima de LIMITE_DUAS_APROVACOES_REAIS, DUAS aprovações de pessoas diferentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.config import get_settings
from app.db.models import PapelVinculo


@dataclass(frozen=True)
class Politica:
    porte: str
    max_usuarios: int
    papeis_convidaveis: tuple[str, ...]
    operador_exige_alcada: bool
    quatro_olhos_acesso: bool
    duas_aprovacoes_acima: Decimal | None
    max_funcionarios: int | None
    resumo: str

    def para_api(self) -> dict:
        return {
            "porte": self.porte, "max_usuarios": self.max_usuarios, "papeis_convidaveis": list(self.papeis_convidaveis),
            "operador_exige_alcada": self.operador_exige_alcada, "quatro_olhos_acesso": self.quatro_olhos_acesso,
            "duas_aprovacoes_acima": str(self.duas_aprovacoes_acima) if self.duas_aprovacoes_acima else None,
            "max_funcionarios": self.max_funcionarios, "resumo": self.resumo,
        }


TODOS = tuple(p.value for p in PapelVinculo)


def politica(porte: str) -> Politica:
    s = get_settings()
    if porte == "MEI":
        return Politica(
            porte="MEI", max_usuarios=1 + max(1, s.mei_max_funcionarios) + 1,
            papeis_convidaveis=(PapelVinculo.OPERADOR.value, PapelVinculo.CONSULTA.value),
            operador_exige_alcada=True, quatro_olhos_acesso=False, duas_aprovacoes_acima=None,
            max_funcionarios=s.mei_max_funcionarios,
            resumo="Dono único: só o titular administra. Acesso extra só como operador (com alçada) ou consulta.",
        )
    if porte == "GRANDE":
        return Politica(
            porte="GRANDE", max_usuarios=500, papeis_convidaveis=TODOS, operador_exige_alcada=True,
            quatro_olhos_acesso=True, duas_aprovacoes_acima=Decimal(str(s.limite_duas_aprovacoes_reais)),
            max_funcionarios=None,
            resumo=("Quatro olhos em pagamentos E na gestão de acesso; operador sempre com alçada; "
                    "valores altos exigem duas aprovações."),
        )
    return Politica(
        porte="PME", max_usuarios=30, papeis_convidaveis=TODOS, operador_exige_alcada=False,
        quatro_olhos_acesso=False, duas_aprovacoes_acima=None, max_funcionarios=None,
        resumo="Vários usuários; acima da alçada outra pessoa aprova; dar poder exige o rosto de quem concede.",
    )


def aprovacoes_necessarias(porte: str, valor: Decimal) -> int:
    p = politica(porte)
    if p.duas_aprovacoes_acima is not None and valor >= p.duas_aprovacoes_acima:
        return 2
    return 1


def mudanca_sensivel(*, papel_atual: str | None, alcada_atual: Decimal | None, papel_novo: str,
                     alcada_nova: Decimal | None) -> bool:
    """Dar mais poder: virar admin/aprovador, ou aumentar a alçada (inclusive
    para "sem limite")."""
    poderosos = (PapelVinculo.ADMIN.value, PapelVinculo.APROVADOR.value)
    if papel_novo in poderosos and papel_atual not in poderosos:
        return True
    if papel_novo == PapelVinculo.ADMIN.value and papel_atual != PapelVinculo.ADMIN.value:
        return True
    if alcada_nova is None and papel_novo != PapelVinculo.CONSULTA.value:
        return alcada_atual is not None or papel_atual is None
    if alcada_atual is not None and alcada_nova is not None and alcada_nova > alcada_atual:
        return True
    return papel_atual is None and papel_novo != PapelVinculo.CONSULTA.value and (alcada_nova or 0) > 0
