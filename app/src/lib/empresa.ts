import type { PapelVinculo, PortePJ, RegimeApuracao } from "./types";

/**
 * Perfis de empresa. O login é sempre da PESSOA (CPF + senha + aparelho), como
 * nos bancos digitais; o porte muda o padrão de governança da conta: quantas
 * pessoas operam, alçadas e dupla aprovação. O certificado e-CNPJ fica para
 * assinar lotes/remessas (futuro), não como porta de entrada no celular.
 */
export interface PortePerfil {
  label: string;
  faturamento: string;
  /** Recomendação de governança para o porte. */
  duplaAprovacao: boolean;
  governanca: string;
}

export const PORTES: Record<PortePJ, PortePerfil> = {
  MEI: {
    label: "MEI",
    faturamento: "até R$ 81 mil/ano",
    duplaAprovacao: false,
    governanca: "Titular único, com biometria — como a conta pessoal.",
  },
  PME: {
    label: "Pequena ou média (ME · EPP)",
    faturamento: "até R$ 4,8 mi/ano",
    duplaAprovacao: false,
    governanca: "Sócios e operadores com alçada; acima dela, outra pessoa aprova.",
  },
  GRANDE: {
    label: "Grande empresa",
    faturamento: "acima de R$ 4,8 mi/ano",
    duplaAprovacao: true,
    governanca: "Vários operadores, alçadas por pessoa e dupla aprovação (maker-checker).",
  },
};

export const REGIMES_APURACAO: Record<RegimeApuracao, { label: string; dica: string }> = {
  regular: {
    label: "Regime regular (IBS/CBS)",
    dica: "Recebimentos de cobranças com nota têm a CBS e o IBS da nota separados no ato.",
  },
  simples: {
    label: "Simples Nacional",
    dica: "O imposto segue no DAS: sem split nos recebimentos.",
  },
  mei: { label: "MEI", dica: "Fora da obrigatoriedade do split." },
};

export const PAPEIS: Record<PapelVinculo, string> = {
  admin: "Administrador(a)",
  aprovador: "Aprovador(a)",
  operador: "Operador(a)",
  consulta: "Só consulta",
};
