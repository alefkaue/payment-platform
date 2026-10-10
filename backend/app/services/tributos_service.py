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

from datetime import datetime, timezone

from fastapi import HTTPException
from decimal import Decimal

from app.core import tempo
from app.core.config import get_settings
from app.repositories.repository import Repositorio


def repassar(repo: Repositorio, *, corte: datetime | None = None) -> dict:
    corte = corte or tempo.inicio_do_dia(tempo.agora())
    r = repo.repassar_tributos(corte)
    return r or {"id": None, "cbs_total": Decimal("0.00"), "ibs_total": Decimal("0.00"), "total": Decimal("0.00"),
                 "corte": corte, "pernas": 0}


def _mes(mes: str | None) -> tuple[datetime, datetime, str]:
    """Início e fim (exclusivo) do mês em horário de Brasília, em UTC. Padrão: o mês corrente."""
    if mes:
        try:
            ano, m = (int(x) for x in mes.split("-"))
            inicio = datetime(ano, m, 1, tzinfo=tempo.BRT)
        except ValueError:
            raise HTTPException(status_code=400, detail="Mês inválido (use AAAA-MM).") from None
    else:
        hoje = tempo.hoje_brt()
        inicio = datetime(hoje.year, hoje.month, 1, tzinfo=tempo.BRT)
    fim = datetime(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1, tzinfo=tempo.BRT)
    return inicio.astimezone(timezone.utc), fim.astimezone(timezone.utc), f"{inicio:%Y-%m}"


def resumo_empresa(repo: Repositorio, conta: dict, mes: str | None = None) -> dict:
    """Apuração DO MÊS (antes somava tudo desde sempre e o app chamava de mês -- R1-41)."""
    desde, ate, periodo = _mes(mes)
    r = repo.resumo_tributos(recebedor_carteira_id=conta["carteira_id"], desde=desde, ate=ate)
    creditos = repo.listar_creditos(conta["empresa_id"])
    total_credito = sum((c["valor"] for c in creditos), Decimal("0.00"))
    retido = r["cbs_retido"] + r["ibs_retido"]
    from app.services.cobranca_service import fase_split

    fase = fase_split()
    observacao = {
        "informativo": "2026 é ano de teste da Reforma: o imposto aparece destacado na nota, mas não é retido "
                       "(o recolhimento está dispensado e o split começa em 2027). Nada saiu do seu caixa.",
        "demonstracao": "Simulação para apresentação: o split ainda não vale; os valores retidos aqui são de teste.",
        "retencao": "O banco separa o imposto destacado na nota no recebimento. Créditos são abatidos pelo fisco "
                    "na apuração; a restituição prevista é uma estimativa.",
    }[fase]
    return {
        **r,
        "periodo": periodo,
        "faturamento": repo.faturamento_cobrancas(conta["carteira_id"], desde, ate),
        # Quanto as notas pagas no mês destacaram de CBS+IBS (o que SERIA retido no informativo).
        "imposto_destacado": repo.imposto_destacado_cobrancas(conta["carteira_id"], desde, ate),
        "creditos_informados": total_credito,
        "restituicao_prevista": min(total_credito, retido),
        "modo_split": "inteligente",
        "split_fase": fase,
        "split_retencao_desde": get_settings().split_retencao_desde,
        "observacao": observacao,
    }
