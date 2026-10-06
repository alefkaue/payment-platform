"""
Split Payment da Reforma Tributária (IBS/CBS, LC 214/2025).

Duas coisas diferentes moram aqui, e não podem ser confundidas:

1. SPLIT DE VERDADE (`split_da_nota`): acontece no pagamento de uma COBRANÇA
   vinculada a uma NF-e/NFS-e. O banco não calcula o imposto -- ele retém a CBS e
   o IBS DESTACADOS NA NOTA (que já foram calculados item a item, com a
   classificação tributária de cada produto/serviço) e o recebedor fica com o
   resto. Transferência comum (Pix entre contas, sócio para empresa, reembolso,
   empréstimo) NUNCA passa por aqui: não é operação tributada.

   Modo usado: "inteligente" (offline) -- retém o valor bruto destacado, sem
   abater crédito na hora. O abatimento em tempo real ("superinteligente")
   depende da plataforma pública da Receita/CGIBS, que ainda não tem padrão
   técnico publicado; a restituição prevista é só informativa (ver
   tributos_service.resumo_empresa).

2. ESTIMATIVA (`estimar`): calculadora do site/app. Usa a tabela de transição
   (CRONOGRAMA) e o fator do regime do setor. Serve para mostrar ordem de
   grandeza, nunca para reter dinheiro.

Arredondamento: cada tributo arredonda a centavo (ROUND_HALF_UP) e o líquido é o
RESTO, então cbs + ibs + liquido == bruto sempre (testado em tests/test_split.py).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import get_settings
from app.core.tempo import hoje_brt

_CENTAVO = Decimal("0.01")

# Alíquotas de REFERÊNCIA estimadas para o regime pleno. Ainda serão fixadas
# pelo Senado (CBS) e pelo Comitê Gestor (IBS); ajuste aqui quando sair o valor
# oficial. Somadas dão os ~26,5% que aparecem no material de divulgação.
CBS_REFERENCIA = Decimal("0.088")
IBS_REFERENCIA = Decimal("0.177")

# Tabela de transição (EC 132/2023 e LC 214/2025):
# - 2026: ano-teste, CBS 0,9% + IBS 0,1%, compensáveis com PIS/Cofins.
# - 2027-2028: PIS/Cofins extintos, CBS cheia; IBS segue 0,1% (0,05% UF + 0,05% município).
#   (A EC prevê uma redução de 0,1 p.p. na CBS nesses dois anos -- conferir na
#   regulamentação antes de usar em produção.)
# - 2029-2032: IBS sobe 10%/20%/30%/40% da referência enquanto ICMS/ISS caem.
# - 2033: IBS pleno; ICMS e ISS extintos.
CRONOGRAMA: dict[int, dict[str, Decimal]] = {
    2026: {"cbs": Decimal("0.009"), "ibs": Decimal("0.001")},
    2027: {"cbs": CBS_REFERENCIA, "ibs": Decimal("0.001")},
    2028: {"cbs": CBS_REFERENCIA, "ibs": Decimal("0.001")},
    2029: {"cbs": CBS_REFERENCIA, "ibs": IBS_REFERENCIA * Decimal("0.1")},
    2030: {"cbs": CBS_REFERENCIA, "ibs": IBS_REFERENCIA * Decimal("0.2")},
    2031: {"cbs": CBS_REFERENCIA, "ibs": IBS_REFERENCIA * Decimal("0.3")},
    2032: {"cbs": CBS_REFERENCIA, "ibs": IBS_REFERENCIA * Decimal("0.4")},
    2033: {"cbs": CBS_REFERENCIA, "ibs": IBS_REFERENCIA},
}

# Fração da alíquota cheia que cada regime paga (LC 214/2025). Na prática a
# redução vale por PRODUTO/SERVIÇO (NCM/NBS), não pela empresa -- por isso só a
# estimativa usa isto; o split real lê o imposto da nota.
REGIMES: dict[str, Decimal] = {
    "padrao": Decimal("1"),
    "reduzido_30": Decimal("0.7"),
    "reduzido_60": Decimal("0.4"),
    "zero": Decimal("0"),
}


@dataclass(frozen=True)
class ResultadoSplit:
    valor_bruto: Decimal
    cbs: Decimal
    ibs: Decimal
    liquido: Decimal
    aplicou_split: bool

    @property
    def imposto_total(self) -> Decimal:
        return self.cbs + self.ibs

    def para_dict(self) -> dict:
        return {
            "valor_bruto": self.valor_bruto,
            "cbs": self.cbs,
            "ibs": self.ibs,
            "liquido": self.liquido,
            "imposto_total": self.imposto_total,
            "aplicou_split": self.aplicou_split,
        }


def _cent(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def sem_split(valor_bruto: Decimal) -> ResultadoSplit:
    v = _cent(valor_bruto)
    return ResultadoSplit(v, Decimal("0.00"), Decimal("0.00"), v, False)


def ano_padrao() -> int:
    vig = get_settings().split_vigencia
    return int(vig) if vig else hoje_brt().year


def aliquotas_do_ano(ano: int | None = None) -> dict[str, Decimal]:
    a = ano if ano is not None else ano_padrao()
    if a < 2026:
        raise ValueError(f"Não há IBS/CBS antes de 2026 (ano pedido: {a}).")
    return CRONOGRAMA[min(a, 2033)]


def split_da_nota(valor_bruto: Decimal, cbs: Decimal, ibs: Decimal) -> ResultadoSplit:
    """Split de uma cobrança com NF-e: retém exatamente o que a nota destaca."""
    bruto = _cent(valor_bruto)
    c, i = _cent(cbs), _cent(ibs)
    if c < 0 or i < 0:
        raise ValueError("CBS e IBS não podem ser negativos.")
    if c + i > bruto:
        raise ValueError("CBS + IBS da nota não podem passar do valor cobrado.")
    if c + i == 0:
        return sem_split(bruto)
    return ResultadoSplit(bruto, c, i, bruto - c - i, True)


def estimar(valor_bruto: Decimal, *, ano: int | None = None, regime: str = "padrao") -> dict:
    """Estimativa para o simulador. Não é usada para reter dinheiro."""
    if regime not in REGIMES:
        raise ValueError(f"Regime desconhecido: {regime!r}. Use um de {list(REGIMES)}.")
    a = ano if ano is not None else ano_padrao()
    aliq = aliquotas_do_ano(a)
    fator = REGIMES[regime]
    bruto = _cent(valor_bruto)
    cbs = _cent(bruto * aliq["cbs"] * fator)
    ibs = _cent(bruto * aliq["ibs"] * fator)
    r = ResultadoSplit(bruto, cbs, ibs, bruto - cbs - ibs, cbs + ibs > 0)
    return {
        **r.para_dict(),
        "ano": a,
        "regime": regime,
        "aliquota_cbs": aliq["cbs"] * fator,
        "aliquota_ibs": aliq["ibs"] * fator,
        "estimativa": True,
    }


def tabela_transicao() -> list[dict]:
    return [{"ano": a, "cbs": v["cbs"], "ibs": v["ibs"]} for a, v in sorted(CRONOGRAMA.items())]
