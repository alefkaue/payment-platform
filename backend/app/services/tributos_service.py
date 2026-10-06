"""
Tributos retidos no split: repasse ao fisco, resumo e créditos.

- O imposto retido fica na conta de sistema TRIBUTOS (transitória). O job
  POST /admin/tributos/repassar leva ao FISCO tudo o que foi retido ANTES do
  início do dia corrente (D+1), marcando as pernas com o id do repasse. Em
  produção isso vira a liquidação para o Tesouro / Comitê Gestor do IBS.
- Créditos de IBS/CBS são INFORMAÇÃO, com fonte e data: declarados pela empresa,
  gerados por estorno de algo já repassado, ou (futuro) consultados na
  plataforma pública. O banco não guarda crédito como dinheiro.
- A "restituição prevista" do resumo é só uma estimativa: menor valor entre o
  crédito informado e o que já foi retido. Quem restitui é o fisco, na apuração.
"""

from datetime import datetime
from decimal import Decimal

from app.core import tempo
from app.repositories.repository import Repositorio


def repassar(repo: Repositorio, *, corte: datetime | None = None) -> dict:
    corte = corte or tempo.inicio_do_dia(tempo.agora())
    r = repo.repassar_tributos(corte)
    return r or {"id": None, "cbs_total": Decimal("0.00"), "ibs_total": Decimal("0.00"), "total": Decimal("0.00"),
                 "corte": corte, "pernas": 0}


def resumo_empresa(repo: Repositorio, conta: dict) -> dict:
    r = repo.resumo_tributos(recebedor_carteira_id=conta["carteira_id"])
    creditos = repo.listar_creditos(conta["empresa_id"])
    total_credito = sum((c["valor"] for c in creditos), Decimal("0.00"))
    retido = r["cbs_retido"] + r["ibs_retido"]
    return {
        **r,
        "creditos_informados": total_credito,
        "restituicao_prevista": min(total_credito, retido),
        "modo_split": "inteligente",
        "observacao": "O banco retém o imposto destacado na nota. Créditos são abatidos pelo fisco na apuração; "
                      "a restituição prevista é uma estimativa.",
    }
