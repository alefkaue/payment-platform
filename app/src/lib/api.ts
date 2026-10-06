/**
 * API seam. Every function mirrors a real backend endpoint's signature and shape.
 * Today they resolve against in-memory mocks; swap bodies for fetch() calls later.
 */
import { calcularSplit } from "./split";
import type {
  ApuracaoPJ,
  Cartao,
  CvvDinamico,
  CarteiraInfo,
  ComprarPassagemPayload,
  ComprarProdutoPayload,
  Conta,
  DepositarPayload,
  Fatura,
  LoginPayload,
  LoginResposta,
  Produto,
  RegistrarPayload,
  ResumoVendasPJ,
  SplitResultado,
  TipoConta,
  Transacao,
  TransferirPayload,
  Voo,
} from "./types";
import {
  apuracaoDemo,
  BANCO_CARTEIRA,
  carteiras,
  cartoes,
  contasDemo,
  faturas,
  genId,
  produtos as PRODUTOS,
  sessao,
  transacoes,
  voos as VOOS,
} from "@/mocks/data";

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}

const delay = (ms = 450) => new Promise((r) => setTimeout(r, ms));
const r2 = (n: number) => Math.round(n * 100) / 100;
const LIMITE_SELFIE = 500;

function carteiraPorId(id: number): CarteiraInfo | undefined {
  return carteiras.find((c) => c.carteira_id === id);
}

// --- Auth -------------------------------------------------------------------
export async function login({ email, senha }: LoginPayload): Promise<LoginResposta> {
  await delay();
  if (!email || !senha) throw new ApiError("Informe e-mail e senha.", 401);
  const ehPJ = /empresa|pj|\bcnpj\b|ltda|me@/i.test(email);
  const base = ehPJ ? contasDemo.PJ : contasDemo.PF;
  sessao.conta = { ...base };
  return { token: "mock-token", conta: { ...sessao.conta } };
}

export async function registrar(p: RegistrarPayload): Promise<LoginResposta> {
  await delay(700);
  if (p.senha.length < 8) throw new ApiError("A senha precisa ter ao menos 8 caracteres.");
  const id = genId();
  const conta: Conta = {
    id,
    nome: p.nome,
    tipo: p.tipo,
    carteira_id: 4000 + id,
    saldo: 0,
    pontos: p.tipo === "PF" ? 0 : 0,
  };
  carteiras.push({ carteira_id: conta.carteira_id, nome: conta.nome, tipo: conta.tipo });
  sessao.conta = { ...conta };
  return { token: "mock-token", conta: { ...conta } };
}

// --- Conta e extrato --------------------------------------------------------
export async function minhaConta(): Promise<Conta> {
  await delay(250);
  return { ...sessao.conta };
}

export async function transacoes_(): Promise<Transacao[]> {
  await delay(350);
  const minha = sessao.conta.carteira_id;
  return transacoes
    .filter((t) => t.origem_carteira_id === minha || t.destino_carteira_id === minha)
    .sort((a, b) => b.criado_em.localeCompare(a.criado_em));
}
export { transacoes_ as transacoes };

export async function transacaoPorId(id: number): Promise<Transacao> {
  await delay(200);
  const t = transacoes.find((x) => x.id === id);
  if (!t) throw new ApiError("Transação não encontrada.", 404);
  return t;
}

export async function consultarCarteira(id: number): Promise<CarteiraInfo> {
  await delay(300);
  const c = carteiraPorId(id);
  if (!c) throw new ApiError("Carteira não encontrada.", 404);
  return { ...c };
}

export async function simularSplit(
  valor: number,
  tipo_destino: TipoConta,
): Promise<SplitResultado> {
  return calcularSplit(valor, tipo_destino);
}

// --- Núcleo: registrar um pagamento (gera split quando o destino é PJ) ------
function registrarPagamento(args: {
  destino: CarteiraInfo;
  valor: number;
  selfie: File | null;
  categoria: Transacao["categoria"];
  descricao: string;
}): Transacao {
  const { destino, valor, selfie, categoria, descricao } = args;
  if (destino.carteira_id === sessao.conta.carteira_id)
    throw new ApiError("Não é possível pagar a própria carteira.");
  if (!(valor > 0)) throw new ApiError("Valor inválido.");
  if (valor > sessao.conta.saldo) throw new ApiError("Saldo insuficiente.");
  if (valor > LIMITE_SELFIE && !selfie)
    throw new ApiError(
      `Selfie obrigatória para valores acima de ${LIMITE_SELFIE.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}.`,
      403,
    );
  const s = calcularSplit(valor, destino.tipo);
  const t: Transacao = {
    id: genId(),
    origem_carteira_id: sessao.conta.carteira_id,
    destino_carteira_id: destino.carteira_id,
    valor_bruto: s.valor_bruto,
    cbs: s.cbs,
    ibs: s.ibs,
    liquido: s.liquido,
    tipo_destino: destino.tipo,
    aplicou_split: s.aplicou_split,
    auth_metodo: selfie ? "selfie" : "senha",
    categoria,
    descricao,
    criado_em: new Date().toISOString(),
  };
  sessao.conta.saldo = r2(sessao.conta.saldo - s.valor_bruto);
  transacoes.push(t);
  return t;
}

export async function transferir(p: TransferirPayload): Promise<Transacao> {
  await delay(800);
  const destino = await consultarCarteira(p.destino_carteira_id);
  const descricao =
    p.descricao ||
    (destino.tipo === "PJ" ? `Pagamento · ${destino.nome}` : `Pix para ${destino.nome}`);
  return registrarPagamento({
    destino,
    valor: p.valor,
    selfie: p.selfie ?? null,
    categoria: destino.tipo === "PJ" ? "compra" : "transferencia",
    descricao,
  });
}

export async function depositar(p: DepositarPayload): Promise<Transacao> {
  await delay(600);
  if (!(p.valor > 0)) throw new ApiError("Valor inválido.");
  const t: Transacao = {
    id: genId(),
    origem_carteira_id: BANCO_CARTEIRA,
    destino_carteira_id: sessao.conta.carteira_id,
    valor_bruto: r2(p.valor),
    cbs: 0,
    ibs: 0,
    liquido: r2(p.valor),
    tipo_destino: sessao.conta.tipo,
    aplicou_split: false,
    auth_metodo: "senha",
    categoria: "deposito",
    descricao: "Depósito via Pix",
    criado_em: new Date().toISOString(),
  };
  sessao.conta.saldo = r2(sessao.conta.saldo + p.valor);
  transacoes.push(t);
  return t;
}

// --- Lojinha virtual (PF) ---------------------------------------------------
export async function listarProdutos(): Promise<Produto[]> {
  await delay(350);
  return [...PRODUTOS];
}

export async function produtoPorId(id: number): Promise<Produto> {
  await delay(200);
  const p = PRODUTOS.find((x) => x.id === id);
  if (!p) throw new ApiError("Produto não encontrado.", 404);
  return { ...p };
}

export async function comprarProduto(p: ComprarProdutoPayload): Promise<Transacao> {
  await delay(800);
  if (sessao.conta.tipo !== "PF")
    throw new ApiError("A Loja é exclusiva para contas Pessoa Física.", 403);
  const produto = await produtoPorId(p.produto_id);
  const destino = await consultarCarteira(produto.merchant_carteira_id);
  const t = registrarPagamento({
    destino,
    valor: produto.preco,
    selfie: p.selfie ?? null,
    categoria: "compra",
    descricao: `${produto.merchant_nome} · ${produto.nome}`,
  });
  sessao.conta.pontos += Math.round(produto.preco); // 1 ponto por real
  return t;
}

// --- Viagens (PF) -----------------------------------------------------------
export async function buscarVoos(origem?: string, destino?: string): Promise<Voo[]> {
  await delay(400);
  return VOOS.filter(
    (v) => (!origem || v.origem === origem) && (!destino || v.destino === destino),
  );
}

export async function vooPorId(id: number): Promise<Voo> {
  await delay(200);
  const v = VOOS.find((x) => x.id === id);
  if (!v) throw new ApiError("Voo não encontrado.", 404);
  return { ...v };
}

export async function comprarPassagem(p: ComprarPassagemPayload): Promise<Transacao> {
  await delay(900);
  if (sessao.conta.tipo !== "PF")
    throw new ApiError("Viagens é um benefício das contas Pessoa Física.", 403);
  const voo = await vooPorId(p.voo_id);
  const destino = await consultarCarteira(voo.merchant_carteira_id);
  const t = registrarPagamento({
    destino,
    valor: voo.preco,
    selfie: p.selfie ?? null,
    categoria: "viagem",
    descricao: `Voo ${voo.origem} → ${voo.destino} · ${voo.companhia}`,
  });
  sessao.conta.pontos += voo.milhas;
  return t;
}

// --- Visão do lojista PJ: vendas recebidas com split -------------------------
export async function resumoVendasPJ(): Promise<ResumoVendasPJ> {
  await delay(400);
  const minha = sessao.conta.carteira_id;
  const vendas = transacoes.filter((t) => t.destino_carteira_id === minha && t.aplicou_split);
  const total_bruto = r2(vendas.reduce((a, t) => a + t.valor_bruto, 0));
  const total_imposto_retido = r2(vendas.reduce((a, t) => a + t.cbs + t.ibs, 0));
  const total_recebido_liquido = r2(vendas.reduce((a, t) => a + t.liquido, 0));
  return { total_recebido_liquido, total_imposto_retido, total_bruto, qtd_vendas: vendas.length };
}

/** Apuração automática do período — o split inteligente abatendo imposto com crédito. */
export async function apuracaoPJ(): Promise<ApuracaoPJ> {
  await delay(400);
  return { ...apuracaoDemo };
}

/** Contas a receber / a pagar (B2B), atreladas a NF-e. */
export async function listarFaturas(direcao?: Fatura["direcao"]): Promise<Fatura[]> {
  await delay(350);
  return faturas
    .filter((f) => !direcao || f.direcao === direcao)
    .sort((a, b) => a.vencimento.localeCompare(b.vencimento));
}

// --- Cartão virtual ---------------------------------------------------------
const PF_NASCE_SEM_CARTAO = false;

/** Cartão virtual da conta logada (cria um na hora se a conta ainda não tem). */
export async function meuCartao(): Promise<Cartao> {
  await delay(300);
  const minha = sessao.conta.carteira_id;
  let c = cartoes.find((x) => x.carteira_id === minha);
  if (!c && !PF_NASCE_SEM_CARTAO) {
    c = {
      id: genId(),
      carteira_id: minha,
      apelido: sessao.conta.tipo === "PJ" ? "Cartão corporativo virtual" : "Cartão virtual",
      numero_masc: `•••• •••• •••• ${1000 + (minha % 9000)}`.replace(/(\d{4})$/, (m) => m),
      bandeira: "Visa",
      validade: "12/31",
      virtual: true,
      estado: "ativo",
      compras_online: true,
      compras_internacionais: false,
      limite: sessao.conta.tipo === "PJ" ? 50000 : 2000,
    };
    cartoes.push(c);
  }
  if (!c) throw new ApiError("Nenhum cartão emitido.", 404);
  return { ...c };
}

/** Atualiza estado/segurança do cartão (congelar, travas de compra). */
export async function atualizarCartao(
  patch: Partial<Pick<Cartao, "estado" | "compras_online" | "compras_internacionais">>,
): Promise<Cartao> {
  await delay(350);
  const minha = sessao.conta.carteira_id;
  const c = cartoes.find((x) => x.carteira_id === minha);
  if (!c) throw new ApiError("Cartão não encontrado.", 404);
  Object.assign(c, patch);
  return { ...c };
}

/** CVV dinâmico: gira a cada 60s — some do app e reduz fraude em compra online. */
export async function cvvDinamico(): Promise<CvvDinamico> {
  await delay(200);
  const cvv = String(Math.floor(100 + Math.random() * 900));
  return { cvv, expira_em: Date.now() + 60_000 };
}
