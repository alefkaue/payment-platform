import type { SplitResultado, TipoConta, Vigencia } from "./types";

export const ALIQUOTAS: Record<Vigencia, { cbs: number; ibs: number }> = {
  "2026": { cbs: 0.009, ibs: 0.001 },
  "2027": { cbs: 0.088, ibs: 0.177 },
};

export const VIGENCIA_ATUAL: Vigencia = "2026";

const r2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;

/** Mirrors backend: cbs/ibs rounded to 2 places; liquido is the remainder. Only PJ is withheld. */
export function calcularSplit(
  valor: number,
  tipo: TipoConta,
  vigencia: Vigencia = VIGENCIA_ATUAL,
): SplitResultado {
  const bruto = r2(valor);
  if (tipo !== "PJ") {
    return {
      valor_bruto: bruto,
      cbs: 0,
      ibs: 0,
      liquido: bruto,
      imposto_total: 0,
      aplicou_split: false,
      vigencia,
    };
  }
  const a = ALIQUOTAS[vigencia];
  const cbs = r2(bruto * a.cbs);
  const ibs = r2(bruto * a.ibs);
  const liquido = r2(bruto - cbs - ibs);
  return {
    valor_bruto: bruto,
    cbs,
    ibs,
    liquido,
    imposto_total: r2(cbs + ibs),
    aplicou_split: true,
    vigencia,
  };
}
