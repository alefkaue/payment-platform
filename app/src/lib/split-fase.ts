import type { SplitFase } from "./types";

export function faseSplitDemo(): SplitFase {
  const fase = import.meta.env["VITE_SPLIT_FASE"];
  return fase === "informativo" || fase === "retencao" ? fase : "demonstracao";
}

export const TEXTO_INFORMATIVO =
  "Em 2026 a Reforma está em teste: o imposto aparece na nota, mas não é retido — você recebeu o valor inteiro. A separação automática começa em 2027.";
export const TEXTO_DEMONSTRACAO =
  "Ambiente de demonstração: o split ainda não vale; os valores são de teste.";
