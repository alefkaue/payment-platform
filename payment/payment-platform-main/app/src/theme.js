// Tokens do design handoff (direção "Fluxo Mono"), convertidos para hex -- o
// React Native não aceita oklch(). Mantém a regra: imposto é sempre âmbar/ocre,
// nunca vermelho (vermelho só em erro).

export const cores = {
  page: "#e4e1d8",
  bg: "#fbfaf7",
  card: "#ffffff",
  ink: "#141414",
  ink3: "#2e2d2a",
  onp: "#ffffff",
  mut: "#6d6a62",
  mut2: "#57554f",
  mut3: "#a3a098",
  tint: "#ecebe5",
  line: "#e6e4dd",
  line2: "#dcd9cf",
  // imposto (âmbar/ocre)
  taxt: "#8a6a2a",
  taxt2: "#6e5420",
  taxbg: "#f6efdf",
  taxbg2: "#efe4cc",
  ocre: "#c99a3a",
  // erro (vermelho, só erro real)
  errbg: "#f7e3df",
  errt: "#9c3326",
  // marca
  marca: "#f2d03b",
};

export const raio = {
  barra: 7,
  voltar: 12,
  botao: 14,
  input: 16,
  aviso: 16,
  cardMenor: 18,
  lista: 20,
  cardPrincipal: 22,
  chip: 999,
};

export const fonte = {
  saldo: 40,
  comprovante: 36,
  tituloLanding: 34,
  tituloTela: 26,
  corpo: 15,
  secundario: 13,
  label: 12.5,
};

export const sombraCard = {
  shadowColor: "#141414",
  shadowOpacity: 0.12,
  shadowRadius: 20,
  shadowOffset: { width: 0, height: 10 },
  elevation: 4,
};

// Formata centavos/reais no padrão brasileiro.
export function moeda(valor) {
  const n = Number(valor || 0);
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
