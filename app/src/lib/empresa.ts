import type { PortePJ } from "./types";

/**
 * Como cada porte de empresa se autentica no banco — a regra de verificação é
 * "mutável" por porte, refletindo a realidade do mercado:
 *  - MEI: titular único → biometria/selfie, como na conta pessoal.
 *  - PME (ME/EPP): certificado digital e-CNPJ do representante legal + token.
 *  - Grande: certificado e-CNPJ A3 em token, múltiplos assinantes e dupla
 *    autorização (maker-checker / alçadas).
 */
export type MetodoAuthPJ = "biometria" | "certificado";

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
    metodo: "certificado",
    duplaAssinatura: false,
    authTitulo: "Entrar com certificado digital",
    authDescricao: "e-CNPJ (ICP-Brasil) do representante legal, com token de acesso.",
  },
  GRANDE: {
    label: "Grande empresa",
    faturamento: "acima de R$ 4,8 mi/ano",
    metodo: "certificado",
    duplaAssinatura: true,
    authTitulo: "Entrar com certificado digital",
    authDescricao: "e-CNPJ A3 em token, com múltiplos assinantes e dupla autorização (alçadas).",
  },
};

/**
 * Descobre o método de entrada a partir do que foi digitado no campo "Conta".
 * Sem backend ainda: um e-mail/documento de empresa cai em certificado digital
 * (a menos que seja MEI, que usa biometria); pessoa física usa biometria.
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
