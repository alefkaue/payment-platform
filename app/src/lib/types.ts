export type TipoConta = "PF" | "PJ";
/** Ano da tabela de transição da Reforma (2026 a 2033). */
export type Vigencia = number;

/** Porte da empresa. */
export type PortePJ = "MEI" | "PME" | "GRANDE";

/** Papel da pessoa numa empresa (conta PJ). */
export type PapelVinculo = "admin" | "aprovador" | "operador" | "consulta";
/** Regime de apuração: só o regular sofre split no recebimento. */
export type RegimeApuracao = "regular" | "simples" | "mei";

/** Resposta a um desafio de prova de vida pedido ao servidor. */
export interface ProvaBiometrica {
  desafio_id: string;
  /** Quadros JPEG em base64 (data URL), sem espelhamento: 1º de frente, depois o movimento. */
  quadros: string[];
}

export interface Desafio {
  desafio_id: string;
  acao: "virar_esquerda" | "virar_direita";
  instrucao: string;
}

/** Para quem vai o dinheiro: chave Pix ou número de conta. */
export interface DestinoRef {
  chave?: string;
  numero?: string;
}

/** Natureza do lançamento no extrato — permite um extrato "de banco de verdade". */
export type CategoriaTx =
  | "transferencia" // Pix/TED entre contas (nunca tem split)
  | "compra" // compra na Loja (pagamento com nota -> split)
  | "viagem" // passagem aérea (pagamento com nota -> split)
  | "deposito" // entrada de dinheiro na conta
  | "recebimento" // dinheiro recebido (visão do PJ)
  | "cobranca" // pagamento de cobrança com nota fiscal (onde o split acontece)
  | "rendimento" // rendimento diário do saldo
  | "estorno"; // devolução (estorno de cobrança ou contestação procedente)

export interface Conta {
  id: number;
  nome: string;
  tipo: TipoConta;
  carteira_id: number;
  /** Agência e número da conta (gerado pelo banco). */
  agencia?: string;
  numero?: string;
  saldo: number;
  /** Valor recebido em bloqueio cautelar (ainda não pode ser usado). */
  saldo_bloqueado?: number;
  /** Pontos de fidelidade (milhas) — usados no benefício de viagens. */
  pontos: number;
  // --- Campos exclusivos de conta Empresa (PJ) ---
  /** CNPJ formatado — exibido no cabeçalho da conta Empresa. */
  cnpj?: string;
  /** Setor/atividade: "Indústria · Autopeças", "Comércio", etc. */
  setor?: string;
  porte?: PortePJ;
  regime_apuracao?: RegimeApuracao;
  /** Papel da pessoa logada nesta empresa e alçada (R$) sem aprovação (null = sem limite). */
  papel?: PapelVinculo;
  alcada?: number | null;
  /**
   * Créditos de IBS/CBS INFORMADOS (declarados ou gerados por estorno). São
   * informação para estimar a restituição na apuração — não dinheiro do banco.
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
  auth_metodo: "senha" | "selfie" | "aprovacao" | "automatico" | "sistema";
  /** concluida | retida (bloqueio cautelar) | devolvida | devolvida_parcial */
  status?: string;
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

/** Destinatário consultado (nome e documento mascarados, como no Pix). */
export interface CarteiraInfo {
  carteira_id: number;
  nome: string;
  tipo: TipoConta;
  documento?: string;
  destino?: DestinoRef;
}

/** Produto da lojinha virtual. O vendedor é sempre uma PJ (compra com nota -> split). */
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

/** Voo do benefício de viagens. Vendido por uma PJ parceira (compra com nota -> split). */
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
/** Login é sempre da PESSOA; ela opera a conta PF e as empresas em que tem vínculo. */
export interface LoginResposta {
  contas: Conta[];
  conta: Conta;
}
export interface EmpresaPayload {
  cnpj: string;
  nome_fantasia?: string;
  porte: PortePJ;
  regime_apuracao: RegimeApuracao;
}
export interface RegistrarPayload {
  nome: string;
  email: string;
  senha: string;
  cpf: string;
  biometria: ProvaBiometrica;
  /** Abrir também a conta da empresa (a pessoa vira admin dela). */
  empresa?: EmpresaPayload;
}
export interface TransferirPayload {
  destino: DestinoRef;
  valor: number;
  biometria?: ProvaBiometrica | null;
  descricao?: string;
}
/** Resultado de uma transferência: concluída, ou pendente de aprovação (PJ acima da alçada). */
export type ResultadoTransferencia =
  | { tipo: "transacao"; transacao: Transacao }
  | { tipo: "pendente"; operacao_id: number; mensagem: string };

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

/** Resumo de vendas de um lojista PJ. */
export interface ResumoVendasPJ {
  total_recebido_liquido: number;
  total_imposto_retido: number;
  total_bruto: number;
  qtd_vendas: number;
}

/**
 * Tributos da conta Empresa — o coração do pitch B2B. No split "inteligente"
 * (modo atual), o banco retém a CBS e o IBS destacados na nota de cada venda
 * paga por cobrança. Os créditos da empresa são abatidos pelo fisco na
 * apuração; a restituição prevista é uma estimativa.
 */
export interface ApuracaoPJ {
  periodo: string; // "Outubro de 2026"
  faturamento: number; // vendas com nota recebidas no período (bruto)
  cbs_retido: number;
  ibs_retido: number;
  imposto_retido: number; // cbs + ibs retidos no ato
  a_repassar: number; // na conta transitória, vai ao fisco em D+1
  repassado: number;
  creditos_informados: number;
  restituicao_prevista: number; // estimativa: min(créditos, retido)
  vendas_com_split: number;
}

/** Cobrança emitida pela empresa (Pix com QR dinâmico + boleto). */
export interface Cobranca {
  id: number;
  txid: string;
  valor: number;
  descricao?: string | null;
  vencimento?: string | null;
  nfe_chave?: string | null;
  cbs: number;
  ibs: number;
  pix_copia_e_cola: string;
  linha_digitavel: string;
  status: "aberta" | "paga" | "cancelada" | "estornada";
  parcela_numero: number;
  parcelas_total: number;
  vai_reter_imposto: boolean;
  recebedor_nome?: string | null;
}

export interface CobrancaPayload {
  valor: number;
  descricao?: string;
  vencimento?: string;
  parcelas?: number;
  nota_fiscal?: { chave: string; cbs: number; ibs: number };
}

export interface Limites {
  por_transacao: number;
  diurno: number;
  noturno: number;
  pendente: {
    por_transacao?: number | null;
    diurno?: number | null;
    noturno?: number | null;
    vigente_em: string;
  } | null;
}

export type EstadoCartao = "ativo" | "congelado";

/**
 * Cartão virtual (100% digital). Modela estado, segurança e limite — o mesmo
 * shape que o backend persiste na tabela `cartoes` (endpoints ainda não expostos).
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
 * Em "receber", o split separa o imposto destacado na nota e credita o líquido.
 * Em "pagar", a compra de insumo gera crédito de IBS/CBS para a apuração.
 */
export interface Fatura {
  id: number;
  direcao: DirecaoFatura;
  contraparte: string; // cliente ou fornecedor ("Mercedes-Benz", "Scania"...)
  nf: string; // "NF-e 0012345"
  valor_bruto: number;
  imposto: number; // IBS + CBS destacados na nota
  liquido: number; // recebível líquido (receber) ou valor líquido pago (pagar)
  credito_gerado: number; // crédito de IBS/CBS gerado (só em "pagar")
  vencimento: string; // ISO
  status: StatusFatura;
}
