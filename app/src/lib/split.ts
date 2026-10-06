import type { SplitResultado, TipoConta, Vigencia } from "./types";

/**
 * Split de IBS/CBS no app — espelha backend/app/services/split_service.py.
 *
 * Regras (v7):
 * - TRANSFERÊNCIA nunca tem split (Pix entre contas não é operação tributada).
 * - O split acontece no pagamento de uma COMPRA/COBRANÇA com nota fiscal: o banco
 *   retém a CBS e o IBS destacados na nota. Aqui no app, quando não temos a nota
 *   (loja, viagens, simulador), estimamos com a tabela de transição abaixo.
 */

/** Alíquotas de referência estimadas (somam ~26,5%). Ajustar quando saírem as oficiais. */
export const CBS_REFERENCIA = 0.088;
export const IBS_REFERENCIA = 0.177;

/**
 * Tabela de transição (EC 132/2023, LC 214/2025):
 * 2026 teste (0,9% + 0,1%); 2027–2028 CBS cheia + IBS 0,1%;
 * 2029–2032 IBS sobe 10/20/30/40% da referência; 2033 IBS pleno.
 */
export const CRONOGRAMA: Record<number, { cbs: number; ibs: number }> = {
  2026: { cbs: 0.009, ibs: 0.001 },
  2027: { cbs: CBS_REFERENCIA, ibs: 0.001 },
  2028: { cbs: CBS_REFERENCIA, ibs: 0.001 },
  2029: { cbs: CBS_REFERENCIA, ibs: IBS_REFERENCIA * 0.1 },
  2030: { cbs: CBS_REFERENCIA, ibs: IBS_REFERENCIA * 0.2 },
  2031: { cbs: CBS_REFERENCIA, ibs: IBS_REFERENCIA * 0.3 },
  2032: { cbs: CBS_REFERENCIA, ibs: IBS_REFERENCIA * 0.4 },
  2033: { cbs: CBS_REFERENCIA, ibs: IBS_REFERENCIA },
};

/** Ano corrente, limitado à tabela (antes de 2026 não há IBS/CBS). */
export const VIGENCIA_ATUAL: Vigencia = Math.min(Math.max(new Date().getFullYear(), 2026), 2033);

export function aliquotasDoAno(ano: Vigencia = VIGENCIA_ATUAL): { cbs: number; ibs: number } {
  return CRONOGRAMA[Math.min(Math.max(ano, 2026), 2033)] ?? { cbs: 0.009, ibs: 0.001 };
}

/** Alíquota do regime pleno (2033): o tamanho do imposto quando a transição acabar. */
export const ALIQUOTA_PLENA = CBS_REFERENCIA + IBS_REFERENCIA;

/**
 * Regimes de alíquota da Reforma — cada setor paga uma fração da alíquota cheia.
 * Na prática a redução vale por PRODUTO/SERVIÇO (NCM/NBS) e vem calculada na
 * nota; aqui serve só para o simulador.
 */
export type RegimeTributario = "padrao" | "reduzido_30" | "reduzido_60" | "zero";

export const REGIMES: Record<RegimeTributario, { label: string; fator: number; exemplos: string }> =
  {
    padrao: {
      label: "Padrão",
      fator: 1,
      exemplos: "Indústria, comércio, autopeças, serviços em geral",
    },
    reduzido_30: {
      label: "Reduzido 30%",
      fator: 0.7,
      exemplos: "Profissões regulamentadas: advocacia, contabilidade, engenharia, medicina…",
    },
    reduzido_60: {
      label: "Reduzido 60%",
      fator: 0.4,
      exemplos: "Saúde, educação, produção agropecuária, cultura",
    },
    zero: { label: "Alíquota zero", fator: 0, exemplos: "Cesta básica nacional" },
  };

/** Alíquota efetiva (fração) de um regime num ano da transição. */
export function aliquotaRegime(regime: RegimeTributario, ano: Vigencia = 2033): number {
  const a = aliquotasDoAno(ano);
  return Math.round((a.cbs + a.ibs) * REGIMES[regime].fator * 10000) / 10000;
}

const r2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;

/**
 * Estimativa do split de uma COMPRA com nota (loja, viagens, simulador). CBS e
 * IBS arredondam ao centavo e o líquido é o resto (soma sempre fecha). Destino
 * PF não retém. Para transferências use `semSplit`.
 */
export function calcularSplit(
  valor: number,
  tipo: TipoConta,
  vigencia: Vigencia = VIGENCIA_ATUAL,
  regime: RegimeTributario = "padrao",
): SplitResultado {
  const bruto = r2(valor);
  if (tipo !== "PJ") return semSplit(bruto, vigencia);
  const a = aliquotasDoAno(vigencia);
  const fator = REGIMES[regime].fator;
  const cbs = r2(bruto * a.cbs * fator);
  const ibs = r2(bruto * a.ibs * fator);
  return {
    valor_bruto: bruto,
    cbs,
    ibs,
    liquido: r2(bruto - cbs - ibs),
    imposto_total: r2(cbs + ibs),
    aplicou_split: cbs + ibs > 0,
    vigencia,
  };
}

/** Transferência: nunca retém imposto. */
export function semSplit(valor: number, vigencia: Vigencia = VIGENCIA_ATUAL): SplitResultado {
  const bruto = r2(valor);
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

/** Descobre o regime a partir do setor/atividade (só para o simulador). */
export function regimeDoSetor(setor?: string): RegimeTributario {
  const s = (setor ?? "").toLowerCase();
  if (/sa[úu]de|educa|agro|cultura|hospital|cl[íi]nica|escola/.test(s)) return "reduzido_60";
  if (/advoc|contab|engenharia|medic|arquitet|regulamentad|consultoria/.test(s))
    return "reduzido_30";
  if (/cesta b[áa]sica/.test(s)) return "zero";
  return "padrao";
}
