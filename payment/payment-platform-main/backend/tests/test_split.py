from decimal import Decimal

import pytest

from app.db.models import TipoPessoa
from app.services import split_service


def test_pf_nao_retem_imposto():
    r = split_service.calcular_split(Decimal("100.00"), TipoPessoa.PF, vigencia="2027")
    assert r.aplicou_split is False
    assert r.cbs == Decimal("0.00")
    assert r.ibs == Decimal("0.00")
    assert r.liquido == Decimal("100.00")


def test_pj_retem_2026_teste():
    # 2026: CBS 0,9% + IBS 0,1% sobre 1000 -> cbs 9,00 / ibs 1,00 / liq 990,00
    r = split_service.calcular_split(Decimal("1000.00"), TipoPessoa.PJ, vigencia="2026")
    assert r.aplicou_split is True
    assert r.cbs == Decimal("9.00")
    assert r.ibs == Decimal("1.00")
    assert r.liquido == Decimal("990.00")


def test_pj_retem_2027_cheia():
    # 2027: CBS 8,8% + IBS 17,7% sobre 1000 -> cbs 88,00 / ibs 177,00 / liq 735,00
    r = split_service.calcular_split(Decimal("1000.00"), TipoPessoa.PJ, vigencia="2027")
    assert r.cbs == Decimal("88.00")
    assert r.ibs == Decimal("177.00")
    assert r.liquido == Decimal("735.00")


@pytest.mark.parametrize("valor", ["0.01", "33.33", "99.99", "1234.56", "7.77", "1000000.00"])
@pytest.mark.parametrize("vig", ["2026", "2027"])
def test_soma_das_pernas_bate_o_bruto(valor, vig):
    # Invariante central: cbs + ibs + liquido == bruto SEMPRE (sem erro de 1 centavo).
    r = split_service.calcular_split(Decimal(valor), TipoPessoa.PJ, vigencia=vig)
    assert r.cbs + r.ibs + r.liquido == Decimal(valor)


def test_vigencia_invalida():
    with pytest.raises(ValueError):
        split_service.calcular_split(Decimal("10.00"), TipoPessoa.PJ, vigencia="1999")
