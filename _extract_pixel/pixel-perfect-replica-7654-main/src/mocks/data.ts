import { calcularSplit } from "@/lib/split";
import type {
  CarteiraInfo,
  CategoriaTx,
  Conta,
  Produto,
  TipoConta,
  Transacao,
  Voo,
} from "@/lib/types";

/** Carteira sintética do "banco" — origem dos depósitos (entrada de dinheiro). */
export const BANCO_CARTEIRA = 0;

let nextId = 500;
export const genId = () => ++nextId;

// --- Contas de demonstração -------------------------------------------------
// Login decide qual conta entra (e-mail com "empresa"/"pj" -> conta PJ).
const contaPF: Conta = {
  id: 42,
  nome: "Marina Alves",
  tipo: "PF",
  carteira_id: 1042,
  saldo: 8420.35,
  pontos: 12450,
};
const contaPJ: Conta = {
  id: 77,
  nome: "Estúdio Norte ME",
  tipo: "PJ",
  carteira_id: 3050,
  saldo: 21875.9,
  pontos: 0,
};

export const contasDemo: Record<TipoConta, Conta> = { PF: contaPF, PJ: contaPJ };

/** Sessão ativa: a conta logada no momento (o api lê e escreve aqui). */
export const sessao: { conta: Conta } = { conta: { ...contaPF } };

// --- Carteiras conhecidas (contatos + lojistas PJ + parceira de viagens) -----
export const carteiras: CarteiraInfo[] = [
  { carteira_id: 1042, nome: "Marina Alves", tipo: "PF" },
  { carteira_id: 2001, nome: "João Pereira", tipo: "PF" },
  { carteira_id: 2002, nome: "Ana Costa", tipo: "PF" },
  { carteira_id: 3050, nome: "Estúdio Norte ME", tipo: "PJ" },
  { carteira_id: 3001, nome: "Padaria Aurora", tipo: "PJ" },
  { carteira_id: 3002, nome: "Mercado Norte", tipo: "PJ" },
  { carteira_id: 3003, nome: "ModaViva", tipo: "PJ" },
  { carteira_id: 3004, nome: "TechPonto", tipo: "PJ" },
  { carteira_id: 3005, nome: "Farmácia Bem", tipo: "PJ" },
  { carteira_id: 3006, nome: "Livraria Sol", tipo: "PJ" },
  { carteira_id: 3100, nome: "PayFlow Viagens", tipo: "PJ" },
];

// --- Lojinha virtual (só contas PF compram; vendedor é sempre PJ) ------------
export const produtos: Produto[] = [
  {
    id: 1,
    nome: "Fones Bluetooth Pulse",
    descricao: "Cancelamento de ruído, 30h de bateria.",
    preco: 349.9,
    categoria: "Eletrônicos",
    emoji: "🎧",
    merchant_carteira_id: 3004,
    merchant_nome: "TechPonto",
  },
  {
    id: 2,
    nome: "Tênis Urban Run",
    descricao: "Leve, respirável, para corrida e dia a dia.",
    preco: 299.0,
    categoria: "Moda",
    emoji: "👟",
    merchant_carteira_id: 3003,
    merchant_nome: "ModaViva",
  },
  {
    id: 3,
    nome: "Cafeteira Italiana",
    descricao: "Café cremoso em casa, 6 xícaras.",
    preco: 159.9,
    categoria: "Casa",
    emoji: "☕",
    merchant_carteira_id: 3002,
    merchant_nome: "Mercado Norte",
  },
  {
    id: 4,
    nome: "Cesta de Pães Artesanais",
    descricao: "Seleção fresca da padaria, entrega no dia.",
    preco: 48.5,
    categoria: "Alimentos",
    emoji: "🥐",
    merchant_carteira_id: 3001,
    merchant_nome: "Padaria Aurora",
  },
  {
    id: 5,
    nome: "Kit Skincare Vitamina C",
    descricao: "Limpeza, sérum e hidratante.",
    preco: 129.9,
    categoria: "Saúde",
    emoji: "🧴",
    merchant_carteira_id: 3005,
    merchant_nome: "Farmácia Bem",
  },
  {
    id: 6,
    nome: "Smartwatch Fit 2",
    descricao: "Monitor cardíaco, GPS e notificações.",
    preco: 629.0,
    categoria: "Eletrônicos",
    emoji: "⌚",
    merchant_carteira_id: 3004,
    merchant_nome: "TechPonto",
  },
  {
    id: 7,
    nome: 'Box de Livros "Clássicos"',
    descricao: "5 obras essenciais em capa dura.",
    preco: 189.9,
    categoria: "Livros",
    emoji: "📚",
    merchant_carteira_id: 3006,
    merchant_nome: "Livraria Sol",
  },
  {
    id: 8,
    nome: "Jaqueta Corta-vento",
    descricao: "Impermeável, dobrável, unissex.",
    preco: 219.9,
    categoria: "Moda",
    emoji: "🧥",
    merchant_carteira_id: 3003,
    merchant_nome: "ModaViva",
  },
];

// --- Benefício de viagens (passagens aéreas) --------------------------------
export const voos: Voo[] = [
  {
    id: 1,
    origem: "GRU",
    origemCidade: "São Paulo",
    destino: "GIG",
    destinoCidade: "Rio de Janeiro",
    companhia: "Azul Linhas",
    saida: "08:15",
    chegada: "09:20",
    duracao: "1h05",
    direto: true,
    preco: 319.9,
    milhas: 9000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
  {
    id: 2,
    origem: "GRU",
    origemCidade: "São Paulo",
    destino: "GIG",
    destinoCidade: "Rio de Janeiro",
    companhia: "LATAM",
    saida: "13:40",
    chegada: "14:50",
    duracao: "1h10",
    direto: true,
    preco: 289.0,
    milhas: 8000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
  {
    id: 3,
    origem: "GRU",
    origemCidade: "São Paulo",
    destino: "SSA",
    destinoCidade: "Salvador",
    companhia: "GOL",
    saida: "06:00",
    chegada: "08:55",
    duracao: "2h55",
    direto: true,
    preco: 612.4,
    milhas: 17000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
  {
    id: 4,
    origem: "GRU",
    origemCidade: "São Paulo",
    destino: "REC",
    destinoCidade: "Recife",
    companhia: "Azul Linhas",
    saida: "22:10",
    chegada: "01:30",
    duracao: "3h20",
    direto: true,
    preco: 748.0,
    milhas: 21000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
  {
    id: 5,
    origem: "CGH",
    origemCidade: "São Paulo",
    destino: "BSB",
    destinoCidade: "Brasília",
    companhia: "LATAM",
    saida: "09:30",
    chegada: "11:10",
    duracao: "1h40",
    direto: true,
    preco: 455.5,
    milhas: 13000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
  {
    id: 6,
    origem: "GRU",
    origemCidade: "São Paulo",
    destino: "POA",
    destinoCidade: "Porto Alegre",
    companhia: "GOL",
    saida: "17:45",
    chegada: "19:25",
    duracao: "1h40",
    direto: false,
    preco: 398.9,
    milhas: 11000,
    merchant_carteira_id: 3100,
    merchant_nome: "PayFlow Viagens",
  },
];

// --- Transações semeadas ----------------------------------------------------
const tipoDe = (carteira: number): TipoConta =>
  carteiras.find((c) => c.carteira_id === carteira)?.tipo ?? "PF";

function mk(
  origem: number,
  destino: number,
  valor: number,
  daysAgo: number,
  categoria: CategoriaTx,
  descricao: string,
  auth: "senha" | "selfie" = "senha",
): Transacao {
  const tipo = categoria === "deposito" ? "PF" : tipoDe(destino);
  const s =
    categoria === "deposito"
      ? { valor_bruto: valor, cbs: 0, ibs: 0, liquido: valor, aplicou_split: false }
      : calcularSplit(valor, tipo);
  return {
    id: ++nextId,
    origem_carteira_id: origem,
    destino_carteira_id: destino,
    valor_bruto: s.valor_bruto,
    cbs: s.cbs,
    ibs: s.ibs,
    liquido: s.liquido,
    tipo_destino: tipo,
    aplicou_split: s.aplicou_split,
    auth_metodo: auth,
    categoria,
    descricao,
    criado_em: new Date(Date.now() - daysAgo * 86400000 - 3600000 * (daysAgo + 2)).toISOString(),
  };
}

export const transacoes: Transacao[] = [
  // Movimentos da conta PF (Marina, 1042)
  mk(1042, 3001, 48.5, 0, "compra", "Padaria Aurora"),
  mk(BANCO_CARTEIRA, 1042, 1500, 1, "deposito", "Depósito via Pix"),
  mk(1042, 2001, 80, 2, "transferencia", "Pix para João Pereira"),
  mk(1042, 3003, 299.0, 3, "compra", "ModaViva · Tênis Urban Run"),
  mk(2002, 1042, 350, 5, "transferencia", "Pix de Ana Costa"),
  mk(1042, 3100, 612.4, 8, "viagem", "Voo GRU → SSA", "selfie"),
  mk(1042, 3004, 629.0, 11, "compra", "TechPonto · Smartwatch Fit 2", "selfie"),

  // Vendas recebidas pela conta PJ (Estúdio Norte, 3050) — o diferencial do split
  mk(2001, 3050, 450, 1, "recebimento", "Venda · João Pereira"),
  mk(2002, 3050, 1280, 2, "recebimento", "Venda · Ana Costa", "selfie"),
  mk(1042, 3050, 320, 4, "recebimento", "Venda · Marina Alves"),
  mk(2001, 3050, 95.9, 6, "recebimento", "Venda · João Pereira"),
];
