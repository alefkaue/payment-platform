export type TipoConta = "PF" | "PJ";
/** Valores da folha permanecem strings decimais, como no servidor. */
export interface Funcionario {
  id: number;
  nome: string;
  cpf: string;
  cargo: string | null;
  salario: string | null;
  ativo: boolean;
}
export interface FuncionarioCreate {
  nome: string;
  cpf: string;
  cargo?: string;
  salario?: string;
}
export interface FolhaItem {
  funcionario_id: number;
  valor?: string;
}
export type ResultadoFolha =
  | { pendente: { id: number; valor: string; aprovacoes_necessarias: number } }
  | {
      resultados: {
        funcionario_id: number;
        situacao: "pago" | "erro";
        transacao_id?: number;
        erro?: string;
      }[];
    };
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

/** Passos de prova de vida que o servidor pode pedir. */
export type PassoBiometria = "piscar2" | "piscar3" | "sorrir" | "virar_esquerda" | "virar_direita";
/** cadastro = as 4 ações; login = 2 ações. Passos e ordem SORTEADOS pelo servidor. */
export type ModoBiometria = "cadastro" | "login";

export interface PassoDesafio {
  id: PassoBiometria;
  instrucao: string;
}

export interface Desafio {
  desafio_id: string;
  modo: ModoBiometria;
  passos: PassoDesafio[];
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
  /** Estado local do MED na demonstração; a API não expõe a contestação no extrato. */
  contestacao_aberta?: boolean;
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
  /** Preço em pontos para resgatar a passagem. */
  milhas: number;
  merchant_carteira_id: number;
  merchant_nome: string;
}

export interface LoginPayload {
  email: string;
  senha: string;
}
/** Login é sempre da PESSOA; ela opera a conta PF e as empresas em que tem vínculo. */
/** Quem está logado (a pessoa; as contas ficam em `contas`). */
export interface Pessoa {
  nome: string;
  email: string;
  /** Só dígitos. */
  cpf?: string;
}
export interface LoginResposta {
  contas: Conta[];
  conta: Conta;
  pessoa?: Pessoa;
}
/**
 * Etapa 1 do login (senha conferida). Falta o 2º fator: o rosto, com o desafio
 * que veio junto. Nenhum token de acesso existe até a etapa 2.
 */
export interface LoginEtapaMfa {
  mfa_token: string;
  desafio: Desafio;
}

/** Documento de identidade para o KYC (imagens em data URL/base64). */
export type TipoDocumentoPessoa = "rg" | "cnh" | "cin" | "passaporte";
export interface DocumentoIdentidade {
  tipo: TipoDocumentoPessoa;
  frente: string;
  verso?: string;
}
/** Resultado da conferência do documento: em análise = vai para uma pessoa revisar. */
export interface KycResultado {
  status: "aprovado" | "em_analise" | "reprovado" | "pendente";
  motivos: string[];
}

export type TipoDocumentoEmpresa =
  "contrato_social" | "ccmei" | "cartao_cnpj" | "procuracao" | "outro";
export interface DocumentoEmpresa {
  tipo: TipoDocumentoEmpresa;
  /** PDF ou imagem em data URL/base64. */
  arquivo: string;
}

export interface EmpresaPayload {
  cnpj: string;
  nome_fantasia?: string;
  porte: PortePJ;
  regime_apuracao: RegimeApuracao;
  setor?: string;
  documentos?: DocumentoEmpresa[];
}
export interface RegistrarPayload {
  nome: string;
  email: string;
  senha: string;
  cpf: string;
  /** AAAA-MM-DD. */
  data_nascimento: string;
  celular: string;
  documento: DocumentoIdentidade | null;
  biometria: ProvaBiometrica;
  /** Abrir também a conta da empresa (a pessoa vira admin dela). */
  empresa?: EmpresaPayload;
}
/** Cadastro feito: falta entrar (senha já conferida; o rosto do login vem a seguir). */
export interface CadastroResposta {
  etapa: LoginEtapaMfa;
  kyc: KycResultado;
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
  biometria?: ProvaBiometrica | null;
}
export interface ComprarPassagemPayload {
  voo_id: number;
  biometria?: ProvaBiometrica | null;
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
  /** Vínculo com o pagamento no banco de demonstração. */
  transacao_id?: number;
  recebedor_carteira_id?: number;
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

/** Aviso na central de notificações (inbox do app). */
export type TipoNotificacao =
  "pagamento" | "cobranca" | "seguranca" | "imposto" | "pontos" | "sistema";
export interface Notificacao {
  id: number;
  tipo: TipoNotificacao;
  titulo: string;
  texto: string;
  criado_em: string; // ISO
  lida: boolean;
  /** Rota do app para onde o toque leva (opcional). */
  href?: "/extrato" | "/contas" | "/split" | "/pendentes" | "/perfil";
}

/** Pessoa com vínculo na empresa (conta PJ) — papel + alçada. */
/**
 * Situação do acesso de uma pessoa à empresa. O admin convida pelo CPF
 * (pendente); na grande empresa, dar poder espera outro admin (aguardando);
 * a pessoa aceita com o próprio rosto (ativo).
 */
export type StatusVinculo = "pendente" | "aguardando" | "ativo" | "suspenso" | "revogado";
export interface MembroEquipe {
  id: number;
  nome: string;
  email: string | null;
  /** Sempre mascarado (***.456.789-**). */
  cpf?: string | null;
  cargo?: string | null;
  papel: PapelVinculo;
  /** Alçada por operação em R$; null = sem limite. */
  alcada: number | null;
  status: StatusVinculo;
  alcada_diaria?: number | null;
  aguardando_aprovacao?: boolean;
  operacao_id?: number | null;
  ativo: boolean;
  ultimo_acesso_em?: string | null;
  /** É a pessoa logada neste momento. */
  eu?: boolean;
}
export interface ConvidarPayload {
  nome: string;
  cpf: string;
  email?: string;
  cargo?: string;
  papel: PapelVinculo;
  alcada: number | null;
  /** Rosto de quem concede (exigido ao dar poder: admin, aprovador, alçada). */
  biometria?: ProvaBiometrica;
}
/** Convite que a PESSOA logada recebeu para acessar uma empresa. */
export interface ConviteRecebido {
  id: number;
  empresa: string;
  papel: PapelVinculo;
  alcada: number | null;
  convidado_por: string | null;
}
/** Regras de acesso do porte (MEI / PME / Grande). */
export interface PoliticaEmpresa {
  porte: PortePJ;
  max_usuarios: number;
  papeis_convidaveis: PapelVinculo[];
  operador_exige_alcada: boolean;
  quatro_olhos_acesso: boolean;
  duas_aprovacoes_acima: number | null;
  resumo: string;
  usuarios_ocupados?: number;
}

/** Operação acima da alçada de quem lançou, aguardando um 2º aprovador (maker-checker). */
export type StatusPendente = "aguardando" | "aprovada" | "recusada";
export type TipoPendente = "transferencia" | "pagamento_cobranca" | "folha" | "acesso";
export interface OperacaoPendente {
  id: number;
  tipo?: TipoPendente;
  descricao: string;
  contraparte: string;
  valor: number;
  criado_por: string;
  criado_em: string; // ISO
  status: StatusPendente;
  /** Grande empresa acima do limite: 2 pessoas diferentes aprovam. */
  aprovacoes_necessarias?: number;
  aprovadores?: string[];
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
  txid?: string;
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

/** Esqueci a senha: etapa 1 feita (e-mail/CPF + nascimento); falta o rosto. */
export interface EtapaRecuperacao {
  token: string;
  desafio: Desafio;
}

/** Aparelho em que a pessoa já entrou (Segurança > Aparelhos). */
export interface Aparelho {
  id: number;
  nome: string | null;
  confiavel: boolean;
  bloqueado: boolean;
  ultimo_uso: string | null;
  criado_em: string | null;
  atual: boolean;
}

/** Sessão aberta (um login com senha + rosto que ainda vale). */
export interface SessaoAtiva {
  sessao_id: string;
  ip: string | null;
  aparelho: string | null;
  ultimo_uso: string | null;
  atual: boolean;
}

/** Linha da trilha de atividade da pessoa. */
export interface Atividade {
  id: number;
  acao: string;
  descricao: string;
  ip: string | null;
  criado_em: string;
}
