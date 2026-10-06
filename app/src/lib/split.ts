import type { SplitResultado, TipoConta, Vigencia } from "./types";

export const ALIQUOTAS: Record<Vigencia, { cbs: number; ibs: number }> = {
  "2026": { cbs: 0.009, ibs: 0.001 },
  "2027": { cbs: 0.088, ibs: 0.177 },
};

export const VIGENCIA_ATUAL: Vigencia = "2026";

/**
 * Alíquota de referência do regime pleno da Reforma (IBS + CBS ≈ 26,5%).
 * Usada nas telas da conta Empresa (B2B), onde o imposto cheio — e o crédito
 * que o abate — são o argumento. A fase 2026 (1%) segue em `ALIQUOTAS`.
 */
export const ALIQUOTA_PLENA = 0.265;

const r2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;

/**
 * Split inteligente (B2B) da LC 214/2025: antes de reter, o sistema consulta os
 * créditos de IBS/CBS acumulados e abate o imposto devido. Só a diferença é
 * recolhida no ato — respeitando a não-cumulatividade do novo IVA.
 */
export function apurarComCredito(impostoDevido: number, creditoDisponivel: number) {
  const devido = r2(Math.max(0, impostoDevido));
  const credito_usado = r2(Math.min(devido, Math.max(0, creditoDisponivel)));
  return {
    imposto_devido: devido,
    credito_usado,
    imposto_recolhido: r2(devido - credito_usado),
    credito_saldo: r2(Math.max(0, creditoDisponivel) - credito_usado),
  };
}

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
