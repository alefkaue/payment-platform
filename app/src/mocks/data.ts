import { calcularSplit } from "@/lib/split";
import type {
  ApuracaoPJ,
  Cartao,
  CarteiraInfo,
  CategoriaTx,
  Conta,
  Fatura,
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
  nome: "Rodoforte Autopeças Ltda",
  tipo: "PJ",
  carteira_id: 3050,
  saldo: 486210.75,
  pontos: 0,
  cnpj: "12.345.678/0001-90",
  setor: "Indústria · Autopeças",
  porte: "GRANDE",
  // Crédito de IBS/CBS acumulado nas compras de aço, energia e componentes.
  creditos: 184300,
};

export const contasDemo: Record<TipoConta, Conta> = { PF: contaPF, PJ: contaPJ };

/**
 * Sessão ativa: a conta logada no momento (o api lê e escreve aqui).
 * Hidrata a partir do sessionStorage para sobreviver a um reload de página
 * (no SPA/apk, um refresh não deve "esquecer" que a conta logada é PJ).
 */
function contaInicial(): Conta {
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem("payflow-session");
      if (raw) {
        const c = JSON.parse(raw)?.conta;
        if (c && (c.tipo === "PF" || c.tipo === "PJ")) return c as Conta;
      }
    } catch {
      /* ignore */
    }
  }
  return { ...contaPF };
}

export const sessao: { conta: Conta } = { conta: contaInicial() };

// --- Carteiras conhecidas (contatos + lojistas PJ + parceira de viagens) -----
export const carteiras: CarteiraInfo[] = [
  { carteira_id: 1042, nome: "Marina Alves", tipo: "PF" },
  { carteira_id: 2001, nome: "João Pereira", tipo: "PF" },
  { carteira_id: 2002, nome: "Ana Costa", tipo: "PF" },
  { carteira_id: 3050, nome: "Rodoforte Autopeças Ltda", tipo: "PJ" },
  { carteira_id: 3200, nome: "Mercedes-Benz do Brasil", tipo: "PJ" },
  { carteira_id: 3201, nome: "Scania Latin America", tipo: "PJ" },
  { carteira_id: 3202, nome: "Usiminas Aços", tipo: "PJ" },
  { carteira_id: 3203, nome: "Energia Sul Distribuidora", tipo: "PJ" },
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

/**
 * Operação B2B industrial (conta Empresa): imposto calculado no regime pleno
 * da Reforma (IBS 17,7% + CBS 8,8% ≈ 26,5%), não na fase de teste de 1%, para
 * que o extrato da Empresa mostre o imposto cheio — e o crédito que o abate.
 */
function mkB2B(
  origem: number,
  destino: number,
  bruto: number,
  daysAgo: number,
  categoria: CategoriaTx,
  descricao: string,
): Transacao {
  const a = { cbs: 0.088, ibs: 0.177 };
  const r = (n: number) => Math.round(n * 100) / 100;
  const cbs = r(bruto * a.cbs);
  const ibs = r(bruto * a.ibs);
  return {
    id: ++nextId,
    origem_carteira_id: origem,
    destino_carteira_id: destino,
    valor_bruto: r(bruto),
    cbs,
    ibs,
    liquido: r(bruto - cbs - ibs),
    tipo_destino: "PJ",
    aplicou_split: true,
    auth_metodo: "senha",
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

  // Conta Empresa (Rodoforte, 3050): vendas B2B recebidas com split no ato…
  mkB2B(3200, 3050, 312450.0, 1, "recebimento", "Venda · Mercedes-Benz · NF-e 0012877"),
  mkB2B(3201, 3050, 188900.0, 2, "recebimento", "Venda · Scania · NF-e 0012861"),
  mkB2B(3200, 3050, 96120.5, 5, "recebimento", "Venda · Mercedes-Benz · NF-e 0012840"),
  // …e compras de insumo que geram crédito de IBS/CBS (categoria "compra" = saída)
  mkB2B(3050, 3202, 142800.0, 3, "compra", "Compra · Usiminas Aços · NF-e 0033120"),
  mkB2B(3050, 3203, 38650.0, 6, "compra", "Compra · Energia Sul · NF-e 0033104"),
];

// --- Conta Empresa (B2B): contas a receber / a pagar atreladas a NF-e ---------
const daysFromNow = (d: number) =>
  new Date(Date.now() + d * 86400000).toISOString();

export const faturas: Fatura[] = [
  {
    id: 9001,
    direcao: "receber",
    contraparte: "Mercedes-Benz do Brasil",
    nf: "NF-e 0012903",
    valor_bruto: 428_900,
    imposto: 113_658.5, // 26,5%
    liquido: 315_241.5,
    credito_gerado: 0,
    vencimento: daysFromNow(4),
    status: "pendente",
  },
  {
    id: 9002,
    direcao: "receber",
    contraparte: "Scania Latin America",
    nf: "NF-e 0012899",
    valor_bruto: 206_500,
    imposto: 54_722.5,
    liquido: 151_777.5,
    credito_gerado: 0,
    vencimento: daysFromNow(9),
    status: "agendado",
  },
  {
    id: 9003,
    direcao: "pagar",
    contraparte: "Usiminas Aços",
    nf: "NF-e 0033188",
    valor_bruto: 167_300,
    imposto: 44_334.5,
    liquido: 167_300,
    credito_gerado: 44_334.5, // compra de insumo gera crédito de IBS/CBS
    vencimento: daysFromNow(2),
    status: "pendente",
  },
  {
    id: 9004,
    direcao: "pagar",
    contraparte: "Energia Sul Distribuidora",
    nf: "NF-e 0033170",
    valor_bruto: 41_200,
    imposto: 10_918,
    liquido: 41_200,
    credito_gerado: 10_918,
    vencimento: daysFromNow(6),
    status: "agendado",
  },
];

// --- Cartões virtuais (100% digital) ------------------------------------------
export const cartoes: Cartao[] = [
  {
    id: 7001,
    carteira_id: 1042, // Marina (PF)
    apelido: "Cartão virtual",
    numero_masc: "•••• •••• •••• 4921",
    bandeira: "Visa",
    validade: "12/30",
    virtual: true,
    estado: "ativo",
    compras_online: true,
    compras_internacionais: false,
    limite: 6000,
  },
  {
    id: 7002,
    carteira_id: 3050, // Rodoforte (PJ)
    apelido: "Cartão corporativo virtual",
    numero_masc: "•••• •••• •••• 8450",
    bandeira: "Visa",
    validade: "09/29",
    virtual: true,
    estado: "ativo",
    compras_online: true,
    compras_internacionais: true,
    limite: 150000,
  },
];

// --- Apuração automática do mês (split inteligente) ---------------------------
const nomeMes = new Date().toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
export const apuracaoDemo: ApuracaoPJ = {
  periodo: nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1),
  faturamento: 597_470.5,
  imposto_devido: 158_329.68, // 26,5% sobre o faturamento
  credito_usado: 132_145.2, // crédito das compras abate o devido (não-cumulatividade)
  imposto_recolhido: 26_184.48, // só a diferença vai ao Fisco, no ato
  credito_saldo: 184_300, // crédito tributário que segue acumulado
  caixa_preservado: 158_329.68, // imposto que nunca passou pelo caixa da empresa
  aliquota_pct: 26.5,
  regime: "Padrão", // autopeças/indústria = regime padrão (sem redução)
};
