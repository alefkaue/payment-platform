import type { PapelVinculo, PortePJ, RegimeApuracao } from "./types";

/**
 * No banco, quem acessa a conta da empresa é sempre uma PESSOA, com
 * reconhecimento facial (prova de vida) — igual à conta pessoal. O que muda por
 * pessoa são o PAPEL e a ALÇADA do vínculo (consultar, operar, aprovar ou
 * administrar). É assim que funciona nos bancos digitais PJ (Nubank, Inter, C6):
 * cada usuário tem a própria credencial e permissões por função.
 *
 * O certificado digital e-CNPJ (ICP-Brasil) NÃO é o login do app: ele serve para
 * assinar documentos/NF-e e integrações, não para entrar na conta.
 */
export type MetodoAuthPJ = "biometria";

export interface PortePerfil {
  label: string;
  faturamento: string;
  metodo: MetodoAuthPJ;
  /** Exige dupla assinatura (um lança, outro aprova) acima de uma alçada. */
  duplaAssinatura: boolean;
  authTitulo: string;
  authDescricao: string;
}

export const PORTES: Record<PortePJ, PortePerfil> = {
  MEI: {
    label: "MEI",
    faturamento: "até R$ 81 mil/ano",
    metodo: "biometria",
    duplaAssinatura: false,
    authTitulo: "Entrar com biometria",
    authDescricao: "Reconhecimento facial do titular — como na conta pessoal.",
  },
  PME: {
    label: "Pequena ou média (ME · EPP)",
    faturamento: "até R$ 4,8 mi/ano",
    metodo: "biometria",
    duplaAssinatura: false,
    authTitulo: "Entrar com biometria",
    authDescricao:
      "Reconhecimento facial de cada pessoa autorizada; o acesso e o que ela pode fazer vêm do papel e da alçada.",
  },
  GRANDE: {
    label: "Grande empresa",
    faturamento: "acima de R$ 4,8 mi/ano",
    metodo: "biometria",
    duplaAssinatura: true,
    authTitulo: "Entrar com biometria",
    authDescricao:
      "Reconhecimento facial por pessoa, vários usuários com papéis e alçadas e dupla autorização (maker-checker) acima da alçada.",
  },
};

/**
 * Descobre, pelo que foi digitado no campo "Conta", se é empresa (PJ) ou pessoa
 * (PF). Em ambos os casos o login é por biometria da pessoa; na PJ, o que ela
 * pode fazer vem do vínculo (papel e alçada).
 */
export function authPorConta(conta: string): {
  ehPJ: boolean;
  porte: PortePJ | null;
  metodo: MetodoAuthPJ;
} {
  const s = conta.toLowerCase();
  const soDigitos = conta.replace(/\D/g, "");
  const ehMEI = /\bmei\b/.test(s);
  const ehPJ =
    ehMEI ||
    /empresa|pj|ltda|\bme\b|epp|s\.?a\.?|cnpj/.test(s) ||
    conta.includes("/") ||
    soDigitos.length === 14;

  if (!ehPJ) return { ehPJ: false, porte: null, metodo: "biometria" };
  const porte: PortePJ = ehMEI ? "MEI" : "GRANDE";
  return { ehPJ: true, porte, metodo: PORTES[porte].metodo };
}

/** Regime de apuração da empresa: só o regular tem split nos recebimentos. */
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

/** Papel da pessoa na empresa (vínculo) — define o que ela pode fazer e a alçada. */
export const PAPEIS: Record<PapelVinculo, string> = {
  admin: "Administrador(a)",
  aprovador: "Aprovador(a)",
  operador: "Operador(a)",
  consulta: "Só consulta",
};
