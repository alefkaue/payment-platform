import { aliquotasDoAno, calcularSplit, semSplit, VIGENCIA_ATUAL } from "@/lib/split";
import type {
  ApuracaoPJ,
  Cartao,
  CarteiraInfo,
  CategoriaTx,
  Cobranca,
  Conta,
  Fatura,
  MembroEquipe,
  Notificacao,
  OperacaoPendente,
  Produto,
  TipoConta,
  Transacao,
  Voo,
} from "@/lib/types";

/** Carteira sintética do "banco" — origem dos depósitos (entrada de dinheiro). */
export const BANCO_CARTEIRA = 0;

let nextId = 500;
export const genId = () => ++nextId;
/** Garante que ids novos não colidam com os já guardados no banco demo (localStorage). */
export function reservarIds(maior: number) {
  if (maior > nextId) nextId = maior;
}

// --- Contas de demonstração -------------------------------------------------
// A mesma pessoa (Marina) opera a conta pessoal e a empresa (é admin dela):
// troca pelo seletor de conta, como no backend (header X-Conta).
const contaPF: Conta = {
  id: 42,
  nome: "Marina Alves",
  tipo: "PF",
  carteira_id: 1042,
  agencia: "0001",
  numero: "1042",
  saldo: 8420.35,
  pontos: 12450,
};
const contaPJ: Conta = {
  id: 77,
  nome: "Rodoforte Autopeças Ltda",
  tipo: "PJ",
  carteira_id: 3050,
  agencia: "0001",
  numero: "3050",
  saldo: 486210.75,
  pontos: 0,
  cnpj: "12.345.678/0001-90",
  setor: "Indústria · Autopeças",
  porte: "GRANDE",
  regime_apuracao: "regular",
  papel: "admin",
  alcada: null,
  // Crédito de IBS/CBS informado (apurado pelo contador) — informação, não saldo.
  creditos: 5_120.4,
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
  { carteira_id: 3100, nome: "Astro Viagens", tipo: "PJ" },
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
    merchant_nome: "Astro Viagens",
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
    merchant_nome: "Astro Viagens",
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
    merchant_nome: "Astro Viagens",
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
    merchant_nome: "Astro Viagens",
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
    merchant_nome: "Astro Viagens",
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
    merchant_nome: "Astro Viagens",
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
  // Transferência e depósito nunca têm split; compra/viagem (com nota) têm.
  const s =
    categoria === "deposito" || categoria === "transferencia"
      ? semSplit(valor)
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
    status: "concluida",
    categoria,
    descricao,
    criado_em: new Date(Date.now() - daysAgo * 86400000 - 3600000 * (daysAgo + 2)).toISOString(),
  };
}

/**
 * Operação B2B com nota fiscal (conta Empresa): o imposto retido é o da tabela
 * de transição do ANO CORRENTE (em 2026, CBS 0,9% + IBS 0,1%). A projeção para
 * o regime pleno (2033) aparece separada na tela, nunca como valor retido hoje.
 */
function mkB2B(
  origem: number,
  destino: number,
  bruto: number,
  daysAgo: number,
  categoria: CategoriaTx,
  descricao: string,
): Transacao {
  const a = aliquotasDoAno(VIGENCIA_ATUAL);
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
    status: "concluida",
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
  // …e compras de insumo com nota (a nota gera crédito de IBS/CBS na apuração)
  mkB2B(3050, 3202, 142800.0, 3, "compra", "Compra · Usiminas Aços · NF-e 0033120"),
  mkB2B(3050, 3203, 38650.0, 6, "compra", "Compra · Energia Sul · NF-e 0033104"),
];

// --- Conta Empresa (B2B): contas a receber / a pagar atreladas a NF-e ---------
const daysFromNow = (d: number) => new Date(Date.now() + d * 86400000).toISOString();
const aliq = aliquotasDoAno(VIGENCIA_ATUAL);
const impostoNota = (bruto: number) => Math.round(bruto * (aliq.cbs + aliq.ibs) * 100) / 100;

export const faturas: Fatura[] = [
  {
    id: 9001,
    direcao: "receber",
    contraparte: "Mercedes-Benz do Brasil",
    nf: "NF-e 0012903",
    valor_bruto: 428_900,
    imposto: impostoNota(428_900),
    liquido: 428_900 - impostoNota(428_900),
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
    imposto: impostoNota(206_500),
    liquido: 206_500 - impostoNota(206_500),
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
    imposto: impostoNota(167_300),
    liquido: 167_300,
    credito_gerado: impostoNota(167_300), // compra de insumo com nota gera crédito na apuração
    vencimento: daysFromNow(2),
    status: "pendente",
  },
  {
    id: 9004,
    direcao: "pagar",
    contraparte: "Energia Sul Distribuidora",
    nf: "NF-e 0033170",
    valor_bruto: 41_200,
    imposto: impostoNota(41_200),
    liquido: 41_200,
    credito_gerado: impostoNota(41_200),
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

// --- Tributos do mês (split "inteligente": retém o que a nota destaca) --------
const nomeMes = new Date().toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
const vendas = transacoes.filter((t) => t.destino_carteira_id === 3050 && t.aplicou_split);
const somar = (f: (t: Transacao) => number) =>
  Math.round(vendas.reduce((a, t) => a + f(t), 0) * 100) / 100;
const cbsRetido = somar((t) => t.cbs);
const ibsRetido = somar((t) => t.ibs);
export const apuracaoDemo: ApuracaoPJ = {
  periodo: nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1),
  faturamento: somar((t) => t.valor_bruto),
  cbs_retido: cbsRetido,
  ibs_retido: ibsRetido,
  imposto_retido: Math.round((cbsRetido + ibsRetido) * 100) / 100,
  a_repassar: Math.round(vendas[0] ? (vendas[0].cbs + vendas[0].ibs) * 100 : 0) / 100, // venda de ontem: vai em D+1
  repassado:
    Math.round((cbsRetido + ibsRetido - (vendas[0] ? vendas[0].cbs + vendas[0].ibs : 0)) * 100) /
    100,
  creditos_informados: contaPJ.creditos ?? 0,
  restituicao_prevista: Math.min(contaPJ.creditos ?? 0, cbsRetido + ibsRetido),
  vendas_com_split: vendas.length,
};

// --- Cobranças emitidas pela empresa (Pix dinâmico + boleto) -----------------
export const cobrancasDemo: Cobranca[] = [];

// --- Central de notificações (inbox) -----------------------------------------
const hAtras = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

export const notificacoesPF: Notificacao[] = [
  {
    id: 9101,
    tipo: "pontos",
    titulo: "Você ganhou 350 pontos",
    texto: "Sua compra na Loja Astro rendeu 350 pontos. Já dá para usar em viagens.",
    criado_em: hAtras(2),
    lida: false,
    href: "/viagens",
  },
  {
    id: 9102,
    tipo: "pagamento",
    titulo: "Pix recebido: R$ 1.200,00",
    texto: "De João Pereira. O valor já está disponível na sua conta.",
    criado_em: hAtras(9),
    lida: false,
    href: "/extrato",
  },
  {
    id: 9103,
    tipo: "imposto",
    titulo: "Seu saldo rendeu hoje",
    texto: "O dinheiro parado na conta rendeu 100% do CDI. Veja no extrato.",
    criado_em: hAtras(26),
    lida: true,
    href: "/extrato",
  },
  {
    id: 9104,
    tipo: "seguranca",
    titulo: "Novo acesso ao app",
    texto: "Entramos na sua conta neste aparelho. Se não foi você, fale com a gente.",
    criado_em: hAtras(49),
    lida: true,
    href: "/perfil",
  },
];

export const notificacoesPJ: Notificacao[] = [
  {
    id: 9201,
    tipo: "cobranca",
    titulo: "Cobrança paga: Mercedes-Benz",
    texto: "A NF-e 0012903 foi paga. Você recebeu o líquido e o IBS/CBS da nota foi separado.",
    criado_em: hAtras(1),
    lida: false,
    href: "/contas",
  },
  {
    id: 9202,
    tipo: "imposto",
    titulo: "Repasse ao Fisco agendado",
    texto: "R$ 3.124,50 de IBS/CBS retido das suas notas será repassado amanhã (D+1).",
    criado_em: hAtras(5),
    lida: false,
    href: "/split",
  },
  {
    id: 9203,
    tipo: "sistema",
    titulo: "1 operação aguardando aprovação",
    texto: "Um pagamento acima da alçada de quem lançou precisa de um 2º aprovador.",
    criado_em: hAtras(7),
    lida: false,
    href: "/pendentes",
  },
  {
    id: 9204,
    tipo: "cobranca",
    titulo: "Cobrança paga: Scania",
    texto: "A NF-e 0012899 foi paga. Crédito de IBS/CBS atualizado na apuração.",
    criado_em: hAtras(28),
    lida: true,
    href: "/contas",
  },
];

// --- Equipe & alçadas da empresa (vínculos) ----------------------------------
export const equipeDemo: MembroEquipe[] = [
  {
    id: 1,
    nome: "Marina Alves",
    email: "marina@rodoforte.com.br",
    papel: "admin",
    alcada: null,
    status: "ativo",
    ativo: true,
    eu: true,
  },
  {
    id: 2,
    nome: "Carlos Nunes",
    email: "carlos@rodoforte.com.br",
    papel: "aprovador",
    alcada: 200000,
    status: "ativo",
    ativo: true,
  },
  {
    id: 3,
    nome: "Beatriz Lima",
    email: "beatriz@rodoforte.com.br",
    papel: "operador",
    alcada: 50000,
    status: "ativo",
    ativo: true,
  },
  {
    id: 4,
    nome: "Diego Rocha",
    email: "diego@rodoforte.com.br",
    papel: "operador",
    alcada: 20000,
    status: "ativo",
    ativo: true,
  },
  {
    id: 5,
    nome: "Escritório Contábil Sul",
    email: "contato@contabilsul.com.br",
    papel: "consulta",
    alcada: 0,
    status: "ativo",
    ativo: true,
  },
];

// --- Operações pendentes de 2º aprovador (maker-checker) ---------------------
export const pendentesDemo: OperacaoPendente[] = [
  {
    id: 8801,
    descricao: "Pagamento de fornecedor — insumos de aço",
    contraparte: "Usiminas Aços",
    valor: 167300,
    criado_por: "Beatriz Lima",
    criado_em: hAtras(3),
    status: "aguardando",
  },
  {
    id: 8802,
    descricao: "Transferência — folha de pagamento",
    contraparte: "Conta salário · lote",
    valor: 92450.8,
    criado_por: "Diego Rocha",
    criado_em: hAtras(20),
    status: "aguardando",
  },
];
