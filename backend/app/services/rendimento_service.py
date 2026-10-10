"""
Rendimento diário do saldo (PF e PJ), como a "conta que rende" dos bancos digitais.

taxa_diaria = ((1 + CDI_ANUAL) ** (1/252) - 1) * RENDIMENTO_PERCENTUAL_CDI
rendimento  = saldo livre * taxa_diaria, arredondado PARA BAIXO no centavo.

Roda uma vez por dia útil (job POST /admin/jobs/rendimento), sai da conta CAIXA
e é idempotente por carteira/dia (tabela `rendimentos`). Saldo bloqueado não
rende. Fora do escopo por enquanto: IR regressivo e IOF (o produto real paga
via CDB de liquidez diária e retém IR no resgate), feriados (só fim de semana é
pulado) e CDI vindo de fonte oficial (hoje é variável de ambiente).
"""

from datetime import date
from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.repositories.repository import Repositorio

_CENTAVO = Decimal("0.01")


def taxa_diaria() -> Decimal:
    s = get_settings()
    t = ((1 + s.cdi_anual) ** (1 / 252) - 1) * s.rendimento_percentual_cdi
    return Decimal(str(round(t, 10)))


def processar(repo: Repositorio, *, data: date | None = None) -> dict:
    hoje = tempo.hoje_brt()
    d = data or hoje
    # O cálculo usa o saldo ATUAL: creditar outro dia (passado ou futuro) inventaria juros
    # sobre um saldo que a carteira não tinha naquele dia (relatório R1-20).
    if d != hoje:
        raise HTTPException(status_code=400, detail="Rendimento só é creditado no próprio dia (o saldo de outro dia não é conhecido).")
    if not tempo.dia_util(d):
        raise HTTPException(status_code=400, detail="Rendimento só é creditado em dia útil.")
    taxa = taxa_diaria()

    def calcular(saldo: Decimal) -> Decimal:
        return (saldo * taxa).quantize(_CENTAVO, rounding=ROUND_DOWN)

    creditados, total = 0, Decimal("0.00")
    for carteira_id in repo.carteiras_para_rendimento():
        r = repo.creditar_rendimento(carteira_id=carteira_id, data=d, taxa_diaria=taxa, calcular=calcular)
        if r:
            creditados += 1
            total += r["valor"]
    return {"data": d, "taxa_diaria": taxa, "carteiras": creditados, "total": total}
