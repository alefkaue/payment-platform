from decimal import Decimal

import pytest

from app.services import split_service as sp


def test_transferencia_comum_nunca_retem():
    r = sp.sem_split(Decimal("100.00"))
    assert r.aplicou_split is False and r.liquido == Decimal("100.00") and r.imposto_total == 0


def test_split_da_nota_retem_o_que_a_nota_destaca():
    r = sp.split_da_nota(Decimal("1000.00"), Decimal("88.00"), Decimal("1.00"))
    assert (r.cbs, r.ibs, r.liquido) == (Decimal("88.00"), Decimal("1.00"), Decimal("911.00"))
    assert r.aplicou_split


def test_split_da_nota_sem_imposto_nao_aplica():
    assert sp.split_da_nota(Decimal("50.00"), Decimal("0"), Decimal("0")).aplicou_split is False


@pytest.mark.parametrize("cbs,ibs", [("-1", "0"), ("60", "50")])
def test_split_da_nota_invalido(cbs, ibs):
    with pytest.raises(ValueError):
        sp.split_da_nota(Decimal("100.00"), Decimal(cbs), Decimal(ibs))


def test_cronograma_2027_ibs_ainda_e_0_1_por_cento():
    a = sp.aliquotas_do_ano(2027)
    assert a["ibs"] == Decimal("0.001")
    assert a["cbs"] == sp.CBS_REFERENCIA


def test_cronograma_ibs_sobe_gradualmente_ate_2033():
    ibs = [sp.aliquotas_do_ano(a)["ibs"] for a in range(2029, 2034)]
    assert ibs == sorted(ibs) and ibs[-1] == sp.IBS_REFERENCIA
    assert sp.aliquotas_do_ano(2040) == sp.aliquotas_do_ano(2033)


def test_antes_de_2026_nao_tem_ibs_cbs():
    with pytest.raises(ValueError):
        sp.aliquotas_do_ano(2025)


def test_estimativa_2026_e_regime_reduzido():
    e = sp.estimar(Decimal("1000.00"), ano=2026)
    assert (e["cbs"], e["ibs"], e["liquido"]) == (Decimal("9.00"), Decimal("1.00"), Decimal("990.00"))
    e60 = sp.estimar(Decimal("1000.00"), ano=2033, regime="reduzido_60")
    assert e60["cbs"] == Decimal("35.20") and e60["ibs"] == Decimal("70.80")
    assert sp.estimar(Decimal("1000.00"), ano=2033, regime="zero")["aplicou_split"] is False


@pytest.mark.parametrize("valor", ["0.01", "33.33", "99.99", "1234.56", "7.77", "1000000.00"])
@pytest.mark.parametrize("ano", [2026, 2027, 2030, 2033])
def test_pernas_somam_o_bruto(valor, ano):
    e = sp.estimar(Decimal(valor), ano=ano)
    assert e["cbs"] + e["ibs"] + e["liquido"] == Decimal(valor)


def test_regime_desconhecido():
    with pytest.raises(ValueError):
        sp.estimar(Decimal("10"), ano=2026, regime="xpto")
