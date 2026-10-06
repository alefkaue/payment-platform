export type TipoConta = "PF" | "PJ";
export type Vigencia = "2026" | "2027";

/** Natureza do lançamento no extrato — permite um extrato "de banco de verdade". */
export type CategoriaTx =
  | "transferencia" // Pix/TED entre pessoas
  | "compra" // compra na Loja (destino é lojista PJ -> split)
  | "viagem" // passagem aérea (destino é a PJ de viagens -> split)
  | "deposito" // entrada de dinheiro na conta
  | "recebimento"; // dinheiro recebido (visão do PJ)

export interface Conta {
  id: number;
  nome: string;
  tipo: TipoConta;
  carteira_id: number;
  saldo: number;
  /** Pontos de fidelidade (milhas) — usados no benefício de viagens. */
  pontos: number;
}

export interface Transacao {
  id: number;
  origem_carteira_id: number;
  destino_carteira_id: number;
  valor_bruto: number;
  cbs: number;
  ibs: number;
  liquido: number;
  tipo_destino: TipoConta;
  aplicou_split: boolean;
  auth_metodo: "senha" | "selfie";
  categoria: CategoriaTx;
  /** Rótulo humano: "Padaria Aurora", "Voo GRU → GIG", "Pix para João". */
  descricao: string;
  criado_em: string;
}

export interface SplitResultado {
  valor_bruto: number;
  cbs: number;
  ibs: number;
  liquido: number;
  imposto_total: number;
  aplicou_split: boolean;
  vigencia: Vigencia;
}

export interface CarteiraInfo {
  carteira_id: number;
  nome: string;
  tipo: TipoConta;
}

/** Produto da lojinha virtual. O vendedor é sempre uma conta PJ (por isso a compra gera split). */
export interface Produto {
  id: number;
  nome: string;
  descricao: string;
  preco: number;
  categoria: string;
  emoji: string;
  merchant_carteira_id: number;
  merchant_nome: string;
}

/** Voo do benefício de viagens. Vendido por uma PJ parceira (gera split). */
export interface Voo {
  id: number;
  origem: string; // IATA, ex "GRU"
  origemCidade: string;
  destino: string;
  destinoCidade: string;
  companhia: string;
  saida: string; // "08:15"
  chegada: string; // "09:20"
  duracao: string; // "1h05"
  direto: boolean;
  preco: number;
  milhas: number;
  merchant_carteira_id: number;
  merchant_nome: string;
}

export interface LoginPayload {
  email: string;
  senha: string;
}
export interface LoginResposta {
  token: string;
  conta: Conta;
}
export interface RegistrarPayload {
  tipo: TipoConta;
  nome: string;
  email: string;
  senha: string;
  documento: string;
  selfie?: File | null;
}
export interface TransferirPayload {
  destino_carteira_id: number;
  valor: number;
  selfie?: File | null;
  descricao?: string;
}
export interface ComprarProdutoPayload {
  produto_id: number;
  selfie?: File | null;
}
export interface ComprarPassagemPayload {
  voo_id: number;
  selfie?: File | null;
}
export interface DepositarPayload {
  valor: number;
}

/** Resumo de vendas de um lojista PJ — o "porquê" do PayFlow para empresas. */
export interface ResumoVendasPJ {
  total_recebido_liquido: number;
  total_imposto_retido: number;
  total_bruto: number;
  qtd_vendas: number;
}
