export type TipoConta = "PF" | "PJ";
export type Vigencia = "2026" | "2027";

/** Porte da empresa (define o método de verificação/assinatura da conta PJ). */
export type PortePJ = "MEI" | "PME" | "GRANDE";

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
  // --- Campos exclusivos de conta Empresa (PJ) ---
  /** CNPJ formatado — exibido no cabeçalho da conta Empresa. */
  cnpj?: string;
  /** Setor/atividade: "Indústria · Autopeças", "Comércio", etc. */
  setor?: string;
  /** Porte: decide a verificação (MEI = biometria; PME/Grande = certificado e-CNPJ). */
  porte?: PortePJ;
  /**
   * Saldo de créditos tributários (IBS/CBS) acumulados nas compras de insumos.
   * No split inteligente, abate o imposto devido nas vendas em tempo real.
   */
  creditos?: number;
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

/**
 * Apuração automática da conta Empresa no período — o coração do pitch B2B.
 * O "split inteligente" da Reforma (LC 214/2025) consulta os créditos de IBS/CBS
 * antes de reter: o imposto devido nas vendas é abatido pelos créditos acumulados
 * nas compras, e só a diferença (imposto_recolhido) vai ao Fisco no ato.
 */
export interface ApuracaoPJ {
  periodo: string; // "Outubro de 2026"
  faturamento: number; // vendas B2B no período (bruto)
  imposto_devido: number; // IBS + CBS incidente sobre as vendas
  credito_usado: number; // crédito abatido do imposto devido (não-cumulatividade)
  imposto_recolhido: number; // o que efetivamente foi ao Fisco (devido − crédito)
  credito_saldo: number; // crédito tributário que sobrou acumulado
  caixa_preservado: number; // imposto que nunca passou pelo caixa da empresa
  aliquota_pct: number; // alíquota efetiva do regime da empresa (ex.: 26.5)
  regime: string; // rótulo do regime ("Padrão", "Reduzido 60%"...)
}

export type EstadoCartao = "ativo" | "congelado";

/**
 * Cartão virtual (100% digital). Modela estado, segurança e limite — o mesmo
 * shape que o backend persiste na tabela `cartoes`.
 */
export interface Cartao {
  id: number;
  carteira_id: number;
  apelido: string; // "Cartão virtual"
  numero_masc: string; // "•••• •••• •••• 4921"
  bandeira: string; // "Visa"
  validade: string; // "12/30"
  virtual: boolean;
  estado: EstadoCartao;
  compras_online: boolean; // trava de segurança
  compras_internacionais: boolean; // trava de segurança
  limite: number; // limite do cartão
}

/** CVV dinâmico (gira a cada janela) — reduz fraude em compra online. */
export interface CvvDinamico {
  cvv: string;
  expira_em: number; // epoch ms
}

export type DirecaoFatura = "receber" | "pagar";
export type StatusFatura = "liquidado" | "pendente" | "agendado";

/**
 * Fatura B2B (contas a pagar / a receber) atrelada a uma nota fiscal eletrônica.
 * Em "receber", o split separa o imposto e credita o líquido.
 * Em "pagar", a compra de insumo gera crédito de IBS/CBS (credito_gerado).
 */
export interface Fatura {
  id: number;
  direcao: DirecaoFatura;
  contraparte: string; // cliente ou fornecedor ("Mercedes-Benz", "Scania"...)
  nf: string; // "NF-e 0012345"
  valor_bruto: number;
  imposto: number; // IBS + CBS da operação
  liquido: number; // recebível líquido (receber) ou valor líquido pago (pagar)
  credito_gerado: number; // crédito de IBS/CBS gerado (só em "pagar")
  vencimento: string; // ISO
  status: StatusFatura;
}
