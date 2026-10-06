"""
Motor de Split Payment da Reforma Tributária (IBS/CBS).

Regra (espelha o design/handoff e a lógica fiscal):
- Transferência para destino PF (ou GOV) -> SEM retenção. Líquido = bruto.
- Transferência para destino PJ -> retém no ato:
    cbs = bruto * aliquota_cbs
    ibs = bruto * aliquota_ibs
    liquido = bruto - cbs - ibs      (o que a empresa efetivamente recebe)
  O cbs + ibs vai para a conta Governo (GOV). A empresa recebe só o líquido.

Alíquotas por vigência (configurável via SPLIT_VIGENCIA):
- "2026" (teste):          CBS 0,9%  + IBS 0,1%
- "2027" (simulação cheia): CBS 8,8%  + IBS 17,7%

Tudo em Decimal, arredondado a 2 casas (centavos) com ROUND_HALF_UP. O arredondamento
é feito em cada imposto e o líquido é o RESTO (bruto - cbs - ibs), garantindo que
cbs + ibs + liquido == bruto EXATAMENTE (nunca sobra/falta 1 centavo por
arredondamento). Isso é verificado em tests/test_split.py.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import get_settings
from app.db.models import TipoPessoa

_CENTAVO = Decimal("0.01")

# Alíquotas como fração (0.0088 = 0,88%). Fonte única; as regras no banco
# (split_regras) são seedadas a partir daqui no boot.
ALIQUOTAS: dict[str, dict[str, Decimal]] = {
    "2026": {"cbs": Decimal("0.009"), "ibs": Decimal("0.001"), "descricao": "Fase de teste 2026"},
    "2027": {"cbs": Decimal("0.088"), "ibs": Decimal("0.177"), "descricao": "Simulação cheia 2027+"},
}


@dataclass(frozen=True)
class ResultadoSplit:
    valor_bruto: Decimal
    cbs: Decimal
    ibs: Decimal
    liquido: Decimal
    aplicou_split: bool
    vigencia: str

    def para_dict(self) -> dict:
        return {
            "valor_bruto": self.valor_bruto,
            "cbs": self.cbs,
            "ibs": self.ibs,
            "liquido": self.liquido,
            "imposto_total": self.cbs + self.ibs,
            "aplicou_split": self.aplicou_split,
            "vigencia": self.vigencia,
        }


def _cent(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def aliquotas_vigentes(vigencia: str | None = None) -> dict[str, Decimal]:
    vig = vigencia or get_settings().split_vigencia
    if vig not in ALIQUOTAS:
        raise ValueError(f"Vigência de split desconhecida: {vig!r}. Use uma de {list(ALIQUOTAS)}.")
    return ALIQUOTAS[vig]


def calcular_split(
    valor_bruto: Decimal, tipo_destino: TipoPessoa, vigencia: str | None = None
) -> ResultadoSplit:
    """Calcula a divisão de UMA transferência. Função pura -- não toca banco."""
    valor_bruto = _cent(Decimal(valor_bruto))
    vig = vigencia or get_settings().split_vigencia

    # Só PJ sofre retenção. PF e GOV recebem o bruto cheio.
    if tipo_destino != TipoPessoa.PJ:
        return ResultadoSplit(valor_bruto, Decimal("0.00"), Decimal("0.00"), valor_bruto, False, vig)

    aliq = aliquotas_vigentes(vig)
    cbs = _cent(valor_bruto * aliq["cbs"])
    ibs = _cent(valor_bruto * aliq["ibs"])
    # Líquido é o RESTO -- garante cbs + ibs + liquido == bruto sem erro de 1 centavo.
    liquido = valor_bruto - cbs - ibs
    return ResultadoSplit(valor_bruto, cbs, ibs, liquido, True, vig)
