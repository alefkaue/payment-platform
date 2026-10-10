/**
 * Camada de dados do app. As telas só importam daqui.
 *
 * Dois modos (ver src/lib/http.ts):
 * - API: com `VITE_API_URL`, fala com o backend FastAPI v7 de verdade.
 * - Demonstração: sem `VITE_API_URL`, usa os mocks de src/mocks/data.ts — útil
 *   para apresentar offline. As regras do mock seguem as do backend
 *   (transferência sem split, split só em compra/cobrança com nota).
 *
 * Cartão virtual e contas a pagar ainda não têm endpoint no backend: no modo API
 * continuam com dados de demonstração.
 */
import { calcularSplit, semSplit, VIGENCIA_ATUAL } from "./split";
import {
  ApiError,
  definirConta,
  del,
  dispositivoId,
  get,
  MODO_API,
  num,
  post,
  postAnonimo,
  requisitar,
  salvarTokens,
} from "./http";
import type {
  ApuracaoPJ,
  Cartao,
  CarteiraInfo,
  Cobranca,
  CobrancaPayload,
  ComprarPassagemPayload,
  CadastroResposta,
  ComprarProdutoPayload,
  Conta,
  ConvidarPayload,
  ConviteRecebido,
  CvvDinamico,
  DepositarPayload,
  Desafio,
  DestinoRef,
  EmpresaPayload,
  Fatura,
  KycResultado,
  Limites,
  LoginEtapaMfa,
  LoginPayload,
  LoginResposta,
  MembroEquipe,
  Notificacao,
  OperacaoPendente,
  Pessoa,
  PoliticaEmpresa,
  Produto,
  ProvaBiometrica,
  RegistrarPayload,
  ResultadoTransferencia,
  SplitResultado,
  TipoConta,
  TipoPendente,
  Transacao,
  TransferirPayload,
  Voo,
} from "./types";
import {
  apuracaoDemo,
  BANCO_CARTEIRA,
  carteiras,
  cartoes,
  cobrancasDemo,
  contasDemo,
  equipeDemo,
  faturas,
  genId,
  notificacoesPF,
  notificacoesPJ,
  pendentesDemo,
  produtos as PRODUTOS,
  sessao,
  transacoes,
  voos as VOOS,
} from "@/mocks/data";
import {
  aguardarEnvio,
  banco,
  cadastrarPessoa,
  hashSenha,
  puxar,
  senhaConfere,
  chavesDa,
  contaPorId,
  contasDa,
  donoDaConta,
  creditar,
  criarChaveDemo,
  guardarConta,
  guardarTransacao,
  MARINA,
  pessoaPorLogin,
  removerChaveDemo,
  resolverChave,
  todasTransacoes,
} from "@/mocks/banco";

export { ApiError, MODO_API };

const delay = (ms = 450) => (MODO_API ? Promise.resolve() : new Promise((r) => setTimeout(r, ms)));
const r2 = (n: number) => Math.round(n * 100) / 100;
const LIMITE_SELFIE = 500;

// =============================================================================
// Conversão backend -> tipos do app
// =============================================================================

interface ContaApi {
  carteira_id: number;
  agencia: string;
  numero: string;
  titular_tipo: TipoConta;
  nome: string | null;
  documento: string | null;
  empresa_id: number | null;
  regime_apuracao: Conta["regime_apuracao"] | null;
  saldo: string;
  saldo_bloqueado: string;
  papel?: Conta["papel"] | null;
  alcada?: string | null;
}

interface ContaResumoApi {
  carteira_id: number;
  nome: string | null;
}

interface TransacaoApi {
  id: number;
  tipo: string;
  origem: ContaResumoApi;
  destino: ContaResumoApi;
  valor_bruto: string;
  cbs: string;
  ibs: string;
  liquido: string;
  tipo_destino: string;
  aplicou_split: boolean;
  auth_metodo: Transacao["auth_metodo"];
  status: string;
  descricao: string | null;
  data_hora: string;
}

interface CobrancaApi {
  id: number;
  txid: string;
  valor: string;
  descricao: string | null;
  vencimento: string | null;
  nfe_chave: string | null;
  cbs: string;
  ibs: string;
  pix_copia_e_cola: string;
  linha_digitavel: string;
  status: Cobranca["status"];
  parcela_numero: number;
  parcelas_total: number;
  vai_reter_imposto: boolean;
  recebedor_nome: string | null;
  pagador_documento: string | null;
}

function fmtCnpj(d: string | null): string | undefined {
  if (!d || d.length !== 14) return undefined;
  return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

function mapConta(c: ContaApi): Conta {
  const conta: Conta = {
    id: c.carteira_id,
    nome: c.nome ?? "Conta",
    tipo: c.titular_tipo,
    carteira_id: c.carteira_id,
    agencia: c.agencia,
    numero: c.numero,
    saldo: num(c.saldo),
    saldo_bloqueado: num(c.saldo_bloqueado),
    pontos: 0,
  };
  const cnpj = fmtCnpj(c.documento);
  if (cnpj) conta.cnpj = cnpj;
  if (c.papel) conta.papel = c.papel;
  if (c.titular_tipo === "PJ") conta.alcada = c.alcada == null ? null : num(c.alcada);
  if (c.regime_apuracao) conta.regime_apuracao = c.regime_apuracao;
  return conta;
}

function mapTransacao(t: TransacaoApi, minha: number): Transacao {
  const entrada = t.destino.carteira_id === minha;
  const outro = (entrada ? t.origem.nome : t.destino.nome) ?? "conta";
  let categoria: Transacao["categoria"];
  switch (t.tipo) {
    case "cobranca":
      categoria = entrada ? "recebimento" : "cobranca";
      break;
    case "deposito":
      categoria = "deposito";
      break;
    case "rendimento":
      categoria = "rendimento";
      break;
    case "estorno":
    case "devolucao":
      categoria = "estorno";
      break;
    default:
      categoria = "transferencia";
  }
  const descricao =
    t.descricao && t.tipo !== "transferencia"
      ? t.descricao
      : entrada
        ? `Pix de ${outro}`
        : `Pix para ${outro}`;
  return {
    id: t.id,
    origem_carteira_id: t.origem.carteira_id,
    destino_carteira_id: t.destino.carteira_id,
    valor_bruto: num(t.valor_bruto),
    cbs: num(t.cbs),
    ibs: num(t.ibs),
    liquido: num(t.liquido),
    tipo_destino: t.tipo_destino === "PJ" ? "PJ" : "PF",
    aplicou_split: t.aplicou_split,
    auth_metodo: t.auth_metodo,
    status: t.status,
    categoria,
    descricao,
    criado_em: t.data_hora,
  };
}

function mapCobranca(c: CobrancaApi): Cobranca {
  return {
    id: c.id,
    txid: c.txid,
    valor: num(c.valor),
    descricao: c.descricao,
    vencimento: c.vencimento,
    nfe_chave: c.nfe_chave,
    cbs: num(c.cbs),
    ibs: num(c.ibs),
    pix_copia_e_cola: c.pix_copia_e_cola,
    linha_digitavel: c.linha_digitavel,
    status: c.status,
    parcela_numero: c.parcela_numero,
    parcelas_total: c.parcelas_total,
    vai_reter_imposto: c.vai_reter_imposto,
    recebedor_nome: c.recebedor_nome,
  };
}

// =============================================================================
// Sessão
// =============================================================================

/** Conta em uso (PF ou uma PJ). O backend recebe no header X-Conta. */
export function selecionarConta(conta: Conta) {
  definirConta(conta.numero ?? null);
  if (!MODO_API) sessao.conta = contaPorId(conta.carteira_id) ?? { ...conta };
}

/** Modo demonstração: traz o banco compartilhado (outro aparelho pode ter mudado). */
async function sincronizar() {
  if (MODO_API) return;
  await puxar();
  const c = contaPorId(sessao.conta.carteira_id);
  if (c) sessao.conta = c;
}

/** Modo demonstração: grava saldo/pontos da conta em uso no banco demo. */
function persistirSessao() {
  if (!MODO_API) guardarConta(sessao.conta);
}

async function contasDaPessoa(): Promise<{ pessoa: Pessoa; contas: Conta[] }> {
  const eu = await get<{ nome: string; email: string; contas: ContaApi[] }>("/auth/eu");
  const pf = eu.contas.find((c) => c.titular_tipo === "PF");
  return {
    pessoa: { nome: eu.nome, email: eu.email, ...(pf?.documento ? { cpf: pf.documento } : {}) },
    contas: eu.contas.map(mapConta),
  };
}

/**
 * Login em DUAS etapas (senha + rosto), como o backend v9 exige.
 * Etapa 1: a senha confere -> volta um `mfa_token` (preso a este aparelho) e o
 * desafio de prova de vida. Nenhum token de acesso existe ainda.
 */
export async function login({ email, senha }: LoginPayload): Promise<LoginEtapaMfa> {
  await delay();
  if (!email || !senha) throw new ApiError("Informe e-mail (ou CPF) e senha.", 401);
  if (MODO_API) {
    definirConta(null);
    salvarTokens(null);
    const r = await post<{
      mfa_requerido: boolean;
      mfa_token: string | null;
      desafio: Desafio | null;
    }>("/auth/login", { email, senha });
    if (!r.mfa_requerido || !r.mfa_token || !r.desafio)
      throw new ApiError("Este login não é de uma pessoa: use o acesso administrativo.", 403);
    return { mfa_token: r.mfa_token, desafio: r.desafio };
  }
  await sincronizar();
  // Demonstração: quem se cadastrou entra na própria conta (senha conferida);
  // e-mail desconhecido cai na Marina, a pessoa do roteiro da apresentação.
  const achada = pessoaPorLogin(email);
  if (achada && !(await senhaConfere(achada, senha)))
    throw new ApiError("E-mail/CPF ou senha incorretos.", 401);
  return { mfa_token: `demo:${achada?.email ?? MARINA.email}`, desafio: desafioDemo("login") };
}

/** Etapa 2: o rosto (prova de vida) confere -> sessão criada, contas carregadas. */
export async function concluirLogin(
  etapa: LoginEtapaMfa,
  prova: ProvaBiometrica,
): Promise<LoginResposta> {
  await delay();
  if (MODO_API) {
    const tk = await post<{ access_token: string; refresh_token: string }>("/auth/login/mfa", {
      mfa_token: etapa.mfa_token,
      biometria: prova,
    });
    salvarTokens(tk);
    const { pessoa, contas } = await contasDaPessoa();
    const conta = contas.find((c) => c.tipo === "PF") ?? contas[0];
    if (!conta) throw new ApiError("Esta pessoa não tem nenhuma conta para operar.", 404);
    selecionarConta(conta);
    return { contas, conta, pessoa };
  }
  await sincronizar();
  const email = etapa.mfa_token.replace(/^demo:/, "");
  const p =
    pessoaPorLogin(email) ?? banco().pessoas.find((x) => x.email === MARINA.email) ?? MARINA;
  const contas = contasDa(p);
  if (!contas.length) contas.push({ ...contasDemo.PF }, { ...contasDemo.PJ });
  const conta = contas.find((c) => c.tipo === "PF") ?? contas[0]!;
  selecionarConta(conta);
  return { contas, conta, pessoa: { nome: p.nome, email: p.email, cpf: p.cpf } };
}

/** O desafio é de uso único: outra tentativa do rosto pede um desafio novo. */
export async function novoDesafioLogin(etapa: LoginEtapaMfa): Promise<LoginEtapaMfa> {
  if (MODO_API)
    return {
      ...etapa,
      desafio: await post<Desafio>("/auth/login/mfa/desafio", { mfa_token: etapa.mfa_token }),
    };
  return { ...etapa, desafio: desafioDemo("login") };
}

/**
 * Abre a conta da pessoa (com KYC: documento + prova de vida de cadastro) e já
 * faz a etapa 1 do login. A empresa (PJ) só é aberta em `concluirCadastro`,
 * depois do rosto do login: no backend, quem abre empresa é a pessoa logada.
 */
export async function registrar(p: RegistrarPayload): Promise<CadastroResposta> {
  await delay(700);
  if (p.senha.length < 10) throw new ApiError("A senha precisa ter ao menos 10 caracteres.");
  if (MODO_API) {
    const conta = await postAnonimo<{ kyc?: KycResultado }>("/usuarios", {
      nome: p.nome,
      email: p.email,
      senha: p.senha,
      cpf: p.cpf,
      data_nascimento: p.data_nascimento,
      celular: p.celular,
      biometria: p.biometria,
      ...(p.documento ? { documento: p.documento } : {}),
    });
    const etapa = await login({ email: p.email, senha: p.senha });
    return { etapa, kyc: conta.kyc ?? { status: "pendente", motivos: [] } };
  }
  await sincronizar();
  const email = p.email.trim().toLowerCase();
  const cpf = p.cpf.replace(/\D/g, "");
  if (pessoaPorLogin(email)) throw new ApiError("Já existe uma conta com este e-mail.", 409);
  if (pessoaPorLogin(cpf)) throw new ApiError("Já existe uma conta com este CPF.", 409);
  const cnpjNovo = p.empresa?.cnpj.replace(/\D/g, "");
  if (
    cnpjNovo &&
    Object.values(banco().contas).some((c) => (c.cnpj ?? "").replace(/\D/g, "") === cnpjNovo)
  )
    throw new ApiError("Esse CNPJ já tem conta na Astro.", 409);
  const id = genId(); // banco() acima já reservou os ids guardados: sem colisão
  const pf: Conta = {
    id,
    nome: p.nome,
    tipo: "PF",
    carteira_id: 4000 + id,
    agencia: "0001",
    numero: `${4000 + id}`,
    saldo: 0,
    pontos: 0,
  };
  const contas: Conta[] = [pf];
  if (p.empresa) {
    const pj: Conta = {
      id: id + 1,
      nome: p.empresa.nome_fantasia || `Empresa ${p.empresa.cnpj}`,
      tipo: "PJ",
      carteira_id: 5000 + id,
      agencia: "0001",
      numero: `${5000 + id}`,
      cnpj: (cnpjNovo ?? "").replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5"),
      saldo: 0,
      pontos: 0,
      porte: p.empresa.porte,
      regime_apuracao: p.empresa.regime_apuracao,
      ...(p.empresa.setor ? { setor: p.empresa.setor } : {}),
      papel: "admin",
      alcada: null,
      creditos: 0,
    };
    contas.push(pj);
  }
  cadastrarPessoa(
    {
      nome: p.nome,
      email,
      senha: await hashSenha(email, p.senha),
      cpf,
      contas: contas.map((c) => c.carteira_id),
    },
    contas,
  );
  await aguardarEnvio();
  return {
    etapa: { mfa_token: `demo:${email}`, desafio: desafioDemo("login") },
    kyc: { status: p.documento ? "aprovado" : "pendente", motivos: [] },
  };
}

/**
 * Etapa 2 do primeiro login e, se for o caso, a abertura da empresa. Se só a
 * empresa falhar (ex.: CNPJ recusado), a pessoa continua logada na conta
 * pessoal e recebe o motivo em `erroEmpresa`.
 */
export async function concluirCadastro(
  etapa: LoginEtapaMfa,
  prova: ProvaBiometrica,
  empresa?: EmpresaPayload,
): Promise<{ resposta: LoginResposta; erroEmpresa?: string }> {
  const r = await concluirLogin(etapa, prova);
  // No modo demonstração a PJ já nasceu junto com a pessoa.
  if (!MODO_API || !empresa) return { resposta: r };
  try {
    const pj = mapConta(await post<ContaApi>("/empresas", empresa));
    if (empresa.setor) pj.setor = empresa.setor;
    return { resposta: { ...r, contas: [...r.contas, pj], conta: pj } };
  } catch (e) {
    return { resposta: r, erroEmpresa: (e as Error).message };
  }
}

export async function sair(refresh = true): Promise<void> {
  if (MODO_API && refresh) {
    try {
      const raw = window.sessionStorage.getItem("payflow-tokens");
      const rt = raw ? (JSON.parse(raw) as { refresh_token?: string }).refresh_token : undefined;
      if (rt) await post("/auth/logout", { refresh_token: rt });
    } catch {
      /* logout é melhor esforço */
    }
  }
  salvarTokens(null);
  definirConta(null);
}

// =============================================================================
// Biometria (prova de vida com desafio do servidor)
// =============================================================================

const INSTRUCAO_DEMO: Record<import("./types").PassoBiometria, string> = {
  piscar2: "Pisque os olhos devagar, 2 vezes",
  piscar3: "Pisque os olhos devagar, 3 vezes",
  sorrir: "Dê um sorriso",
  virar_esquerda: "Vire o rosto para a sua esquerda",
  virar_direita: "Vire o rosto para a sua direita",
};

/** Demonstração: sorteia como o servidor (login = 2 ações; cadastro = as 4). */
function passosDemo(modo: import("./types").ModoBiometria): import("./types").PassoDesafio[] {
  const acoes: import("./types").PassoBiometria[] = [
    Math.random() < 0.5 ? "piscar2" : "piscar3",
    "sorrir",
    "virar_esquerda",
    "virar_direita",
  ];
  for (let i = acoes.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [acoes[i], acoes[j]] = [acoes[j]!, acoes[i]!];
  }
  return acoes
    .slice(0, modo === "login" ? 2 : 4)
    .map((id) => ({ id, instrucao: INSTRUCAO_DEMO[id] }));
}

function desafioDemo(modo: import("./types").ModoBiometria): Desafio {
  return { desafio_id: `demo-${Date.now()}`, modo, passos: passosDemo(modo) };
}

export async function pedirDesafio(
  modo: import("./types").ModoBiometria = "login",
): Promise<Desafio> {
  // O desafio de cadastro não pode ficar preso a quem estiver logado neste
  // navegador: o servidor só aceita desafio livre em POST /usuarios.
  if (MODO_API)
    return modo === "cadastro"
      ? postAnonimo<Desafio>("/biometria/desafios", { modo })
      : post<Desafio>("/biometria/desafios", { modo });
  return desafioDemo(modo);
}

// =============================================================================
// Conta e extrato
// =============================================================================

export async function minhaConta(): Promise<Conta> {
  await delay(250);
  if (MODO_API) {
    const c = mapConta(await get<ContaApi>("/contas/atual"));
    // Pontos (Loja/Viagens) estão arquivados: app/src/_arquivado/beneficios.
    if (c.tipo === "PJ") {
      const e = await get<{ porte: Conta["porte"]; cnae: string | null; setor: string | null }>(
        "/empresas/atual",
      );
      if (e.porte) c.porte = e.porte;
      if (e.setor) c.setor = e.setor;
      else if (e.cnae) c.setor = `CNAE ${e.cnae}`;
      const creditos = await get<{ valor: string }[]>("/empresas/atual/creditos");
      c.creditos = creditos.reduce((s, x) => s + num(x.valor), 0);
    }
    return c;
  }
  // Outra conta (outro aparelho/aba) pode ter mandado Pix: relê o saldo guardado.
  await puxar();
  const atual = contaPorId(sessao.conta.carteira_id);
  if (atual) sessao.conta = atual;
  return { ...sessao.conta };
}

/** Nome de uma carteira no modo demonstração (contas cadastradas ou contatos semeados). */
function nomeDaCarteira(id: number): string {
  return contaPorId(id)?.nome ?? carteiras.find((c) => c.carteira_id === id)?.nome ?? "conta";
}

export async function transacoes_(): Promise<Transacao[]> {
  await delay(350);
  if (MODO_API) {
    const c = await get<ContaApi>("/contas/atual");
    const ts = await get<TransacaoApi[]>("/pagamentos/transacoes?limite=100");
    return ts.map((t) => mapTransacao(t, c.carteira_id));
  }
  await sincronizar();
  const minha = sessao.conta.carteira_id;
  return todasTransacoes()
    .filter((t) => t.origem_carteira_id === minha || t.destino_carteira_id === minha)
    .map((t) =>
      // Quem recebe um Pix vê "Pix de <quem mandou>", não a descrição de quem enviou.
      t.categoria === "transferencia" &&
      t.destino_carteira_id === minha &&
      t.descricao?.startsWith("Pix para")
        ? { ...t, descricao: `Pix de ${nomeDaCarteira(t.origem_carteira_id)}` }
        : t,
    )
    .sort((a, b) => b.criado_em.localeCompare(a.criado_em));
}
export { transacoes_ as transacoes };

export async function transacaoPorId(id: number): Promise<Transacao> {
  await delay(200);
  if (MODO_API) {
    const c = await get<ContaApi>("/contas/atual");
    return mapTransacao(await get<TransacaoApi>(`/pagamentos/transacoes/${id}`), c.carteira_id);
  }
  await sincronizar();
  const t = todasTransacoes().find((x) => x.id === id);
  if (!t) throw new ApiError("Transação não encontrada.", 404);
  return t;
}

/** Contesta uma transação (golpe/erro) — espelha o MED do Pix. */
export async function contestar(id: number, motivo: string): Promise<void> {
  if (MODO_API) {
    await post(`/pagamentos/transacoes/${id}/contestar`, { motivo });
    return;
  }
  await delay();
}

/**
 * Quem recebe: aceita chave Pix (CPF, CNPJ, e-mail, celular, aleatória) ou
 * número de conta. Devolve nome e documento mascarados, como no Pix.
 */
export async function consultarDestino(texto: string): Promise<CarteiraInfo> {
  await delay(300);
  const alvo = texto.trim();
  if (!alvo) throw new ApiError("Informe a chave Pix ou o número da conta.");
  if (MODO_API) {
    const r = await get<{ nome: string; documento: string; titular_tipo: TipoConta }>(
      `/pix/consultar/${encodeURIComponent(alvo)}`,
    );
    const destino: DestinoRef = /^\d{8}-\d$/.test(alvo) ? { numero: alvo } : { chave: alvo };
    return { carteira_id: 0, nome: r.nome, tipo: r.titular_tipo, documento: r.documento, destino };
  }
  await sincronizar();
  // Primeiro como chave Pix; senão, como número de conta.
  const id = resolverChave(alvo) ?? (/^[\d-]+$/.test(alvo) ? Number(alvo.replace(/\D/g, "")) : NaN);
  const conta = contaPorId(id);
  const c = conta
    ? { carteira_id: conta.carteira_id, nome: conta.nome, tipo: conta.tipo }
    : carteiras.find((x) => x.carteira_id === id);
  if (!c) throw new ApiError("Chave Pix ou conta não encontrada.", 404);
  return { ...c, destino: { numero: String(c.carteira_id) } };
}

export async function simularSplit(
  valor: number,
  tipo_destino: TipoConta,
): Promise<SplitResultado> {
  return calcularSplit(valor, tipo_destino);
}

/**
 * Modo demonstração: as contas do roteiro (Marina e Rodoforte) têm histórico,
 * equipe, notas e notificações semeados; uma conta recém-criada começa vazia.
 */
function ehContaDoRoteiro(): boolean {
  const id = sessao.conta.carteira_id;
  return id === contasDemo.PF.carteira_id || id === contasDemo.PJ.carteira_id;
}

// --- Núcleo do modo demonstração: registra um pagamento -----------------------
function registrarPagamento(args: {
  destino: CarteiraInfo;
  valor: number;
  comBiometria: boolean;
  categoria: Transacao["categoria"];
  descricao: string;
}): Transacao {
  const { destino, valor, comBiometria, categoria, descricao } = args;
  if (destino.carteira_id === sessao.conta.carteira_id)
    throw new ApiError("Não é possível pagar a própria conta.");
  if (!(valor > 0)) throw new ApiError("Valor inválido.");
  if (valor > sessao.conta.saldo) throw new ApiError("Saldo insuficiente.");
  if (valor > LIMITE_SELFIE && !comBiometria)
    throw new ApiError("Valores acima de R$ 500,00 exigem verificação facial.", 400);
  // Transferência nunca tem split; compra com nota (loja/viagens) tem.
  const s = categoria === "transferencia" ? semSplit(valor) : calcularSplit(valor, destino.tipo);
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
    auth_metodo: comBiometria ? "selfie" : "senha",
    status: "concluida",
    categoria,
    descricao,
    criado_em: new Date().toISOString(),
  };
  sessao.conta.saldo = r2(sessao.conta.saldo - s.valor_bruto);
  persistirSessao();
  creditar(destino.carteira_id, s.liquido);
  guardarTransacao(t);
  return t;
}

export async function transferir(p: TransferirPayload): Promise<ResultadoTransferencia> {
  await delay(800);
  if (MODO_API) {
    const r = await requisitar<TransacaoApi | { operacao_id: number; mensagem: string }>(
      "POST",
      "/pagamentos/transferir",
      {
        destino: p.destino,
        valor: p.valor.toFixed(2),
        descricao: p.descricao,
        biometria: p.biometria ?? undefined,
        idempotency_key: `${dispositivoId()}-${Date.now()}`,
      },
    );
    if (r.status === 202) {
      const d = r.dados as { operacao_id: number; mensagem: string };
      return { tipo: "pendente", operacao_id: d.operacao_id, mensagem: d.mensagem };
    }
    const c = await get<ContaApi>("/contas/atual");
    return { tipo: "transacao", transacao: mapTransacao(r.dados as TransacaoApi, c.carteira_id) };
  }
  const destino = await consultarDestino(p.destino.chave ?? p.destino.numero ?? "");
  const t = registrarPagamento({
    destino,
    valor: p.valor,
    comBiometria: Boolean(p.biometria),
    categoria: "transferencia",
    descricao: p.descricao || `Pix para ${destino.nome}`,
  });
  await aguardarEnvio();
  return { tipo: "transacao", transacao: t };
}

/** Depósito: no modo API o dinheiro entra por Pix para uma chave sua (ou pelo admin). */
export async function depositar(p: DepositarPayload): Promise<Transacao> {
  await delay(600);
  if (MODO_API) {
    // Servidor de demonstração (DEPOSITO_DEMO=1) libera dinheiro de teste; num servidor
    // real o endpoint responde 403 e a mensagem explica como colocar dinheiro.
    try {
      const c = await get<ContaApi>("/contas/atual");
      const t = await post<TransacaoApi>("/pagamentos/depositar-demo", {
        valor: p.valor.toFixed(2),
      });
      return mapTransacao(t, c.carteira_id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403)
        throw new ApiError(
          "Para colocar dinheiro, faça um Pix para uma das suas chaves. O depósito direto é só para a equipe (admin).",
          403,
        );
      throw e;
    }
  }
  if (!(p.valor > 0)) throw new ApiError("Valor inválido.");
  await sincronizar();
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
    status: "concluida",
    categoria: "deposito",
    descricao: "Depósito via Pix",
    criado_em: new Date().toISOString(),
  };
  sessao.conta.saldo = r2(sessao.conta.saldo + p.valor);
  persistirSessao();
  guardarTransacao(t);
  await aguardarEnvio();
  return t;
}

// =============================================================================
// Chaves Pix, limites e aparelho
// =============================================================================

export interface ChavePix {
  id: number;
  tipo: string;
  valor: string;
}

export async function minhasChaves(): Promise<ChavePix[]> {
  if (MODO_API) return get<ChavePix[]>("/pix/chaves");
  await sincronizar();
  return chavesDa(sessao.conta.carteira_id).map(({ id, tipo, valor }) => ({ id, tipo, valor }));
}

export async function criarChave(tipo: string, valor?: string): Promise<ChavePix> {
  if (MODO_API) return post<ChavePix>("/pix/chaves", { tipo, valor: valor || undefined });
  await delay(300);
  await sincronizar(); // e reserva os ids já guardados antes de gerar um novo
  try {
    const { id, tipo: t, valor: v } = criarChaveDemo(sessao.conta, tipo, valor, genId());
    await aguardarEnvio();
    return { id, tipo: t, valor: v };
  } catch (e) {
    throw new ApiError((e as Error).message, 400);
  }
}

export async function removerChave(id: number): Promise<void> {
  if (MODO_API) {
    await requisitar("DELETE", `/pix/chaves/${id}`);
    return;
  }
  await sincronizar();
  if (!removerChaveDemo(sessao.conta.carteira_id, id))
    throw new ApiError("Chave não encontrada.", 404);
  await aguardarEnvio();
}

interface LimitesApi {
  por_transacao: string;
  diurno: string;
  noturno: string;
  pendente: {
    por_transacao: string | null;
    diurno: string | null;
    noturno: string | null;
    vigente_em: string;
  } | null;
}

function mapLimites(l: LimitesApi): Limites {
  return {
    por_transacao: num(l.por_transacao),
    diurno: num(l.diurno),
    noturno: num(l.noturno),
    pendente: l.pendente && {
      por_transacao: l.pendente.por_transacao == null ? null : num(l.pendente.por_transacao),
      diurno: l.pendente.diurno == null ? null : num(l.pendente.diurno),
      noturno: l.pendente.noturno == null ? null : num(l.pendente.noturno),
      vigente_em: l.pendente.vigente_em,
    },
  };
}

const limitesDemo: Limites = { por_transacao: 5000, diurno: 10000, noturno: 1000, pendente: null };

export async function meusLimites(): Promise<Limites> {
  if (MODO_API) return mapLimites(await get<LimitesApi>("/seguranca/limites"));
  await delay(200);
  return sessao.conta.tipo === "PJ"
    ? { por_transacao: 50000, diurno: 200000, noturno: 20000, pendente: null }
    : { ...limitesDemo };
}

/** Reduzir vale na hora; aumentar só depois de 24h (carência contra golpe). */
export async function alterarLimites(
  novos: Partial<Pick<Limites, "por_transacao" | "diurno" | "noturno">>,
): Promise<Limites> {
  if (MODO_API) {
    const corpo = Object.fromEntries(
      Object.entries(novos).map(([k, v]) => [k, v == null ? null : v.toFixed(2)]),
    );
    return mapLimites((await requisitar<LimitesApi>("PUT", "/seguranca/limites", corpo)).dados);
  }
  await delay(300);
  Object.assign(limitesDemo, novos);
  return { ...limitesDemo };
}

export async function aparelhoAtual(): Promise<{ confiavel: boolean }> {
  if (MODO_API) return get<{ confiavel: boolean }>("/seguranca/dispositivos/atual");
  return { confiavel: true };
}

export async function confiarAparelho(prova: import("./types").ProvaBiometrica): Promise<void> {
  if (MODO_API) await post("/seguranca/dispositivos/atual/confiar", prova);
}

// =============================================================================
// Empresa: tributos (split), cobranças e contas
// =============================================================================

export async function apuracaoPJ(): Promise<ApuracaoPJ> {
  await delay(400);
  if (MODO_API) {
    const t = await get<{
      cbs_retido: string;
      ibs_retido: string;
      cbs_repassado: string;
      ibs_repassado: string;
      a_repassar: string;
      creditos_informados: string;
      restituicao_prevista: string;
      transacoes_com_split: number;
    }>("/empresas/atual/tributos");
    const cobs = await get<CobrancaApi[]>("/cobrancas?status=paga&limite=200");
    const mes = new Date().toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
    return {
      periodo: mes.charAt(0).toUpperCase() + mes.slice(1),
      faturamento: cobs.reduce((s, c) => s + num(c.valor), 0),
      cbs_retido: num(t.cbs_retido),
      ibs_retido: num(t.ibs_retido),
      imposto_retido: num(t.cbs_retido) + num(t.ibs_retido),
      a_repassar: num(t.a_repassar),
      repassado: num(t.cbs_repassado) + num(t.ibs_repassado),
      creditos_informados: num(t.creditos_informados),
      restituicao_prevista: num(t.restituicao_prevista),
      vendas_com_split: t.transacoes_com_split,
    };
  }
  if (ehContaDoRoteiro()) return { ...apuracaoDemo };
  // Conta criada agora: apura só as vendas com nota que ela recebeu de fato.
  const minha = sessao.conta.carteira_id;
  const vendas = todasTransacoes().filter(
    (t) => t.destino_carteira_id === minha && t.aplicou_split,
  );
  const soma = (f: (t: Transacao) => number) => r2(vendas.reduce((a, t) => a + f(t), 0));
  const cbs = soma((t) => t.cbs);
  const ibs = soma((t) => t.ibs);
  const creditos = sessao.conta.creditos ?? 0;
  const mes = new Date().toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return {
    periodo: mes.charAt(0).toUpperCase() + mes.slice(1),
    faturamento: soma((t) => t.valor_bruto),
    cbs_retido: cbs,
    ibs_retido: ibs,
    imposto_retido: r2(cbs + ibs),
    a_repassar: r2(cbs + ibs),
    repassado: 0,
    creditos_informados: creditos,
    restituicao_prevista: Math.min(creditos, r2(cbs + ibs)),
    vendas_com_split: vendas.length,
  };
}

/** Cobranças emitidas pela conta em uso (no modo demonstração ficam em memória). */
const minhasCobrancasDemo = () =>
  cobrancasDemo.filter((c) => c.recebedor_nome === sessao.conta.nome);

export async function listarCobrancas(): Promise<Cobranca[]> {
  await delay(300);
  if (MODO_API) return (await get<CobrancaApi[]>("/cobrancas?limite=100")).map(mapCobranca);
  return minhasCobrancasDemo().sort((a, b) => b.id - a.id);
}

/** A empresa cobra um cliente. Com a nota fiscal, o pagamento retém a CBS e o IBS dela. */
export async function criarCobranca(p: CobrancaPayload): Promise<Cobranca[]> {
  await delay(500);
  if (MODO_API) {
    const corpo = {
      valor: p.valor.toFixed(2),
      descricao: p.descricao,
      vencimento: p.vencimento,
      parcelas: p.parcelas ?? 1,
      nota_fiscal: p.nota_fiscal && {
        chave: p.nota_fiscal.chave,
        cbs: p.nota_fiscal.cbs.toFixed(2),
        ibs: p.nota_fiscal.ibs.toFixed(2),
      },
    };
    return (await post<CobrancaApi[]>("/cobrancas", corpo)).map(mapCobranca);
  }
  if (p.nota_fiscal && p.nota_fiscal.cbs + p.nota_fiscal.ibs > p.valor)
    throw new ApiError("CBS + IBS da nota não podem passar do valor cobrado.");
  const txid = crypto.randomUUID().replace(/-/g, "");
  const c: Cobranca = {
    id: genId(),
    txid,
    valor: p.valor,
    descricao: p.descricao ?? null,
    vencimento: p.vencimento ?? null,
    nfe_chave: p.nota_fiscal?.chave ?? null,
    cbs: p.nota_fiscal?.cbs ?? 0,
    ibs: p.nota_fiscal?.ibs ?? 0,
    pix_copia_e_cola: `ASTRO-SIMULADO.${txid}`,
    linha_digitavel: "0".repeat(47),
    status: "aberta",
    parcela_numero: 1,
    parcelas_total: 1,
    vai_reter_imposto: Boolean(p.nota_fiscal && p.nota_fiscal.cbs + p.nota_fiscal.ibs > 0),
    recebedor_nome: sessao.conta.nome,
  };
  cobrancasDemo.push(c);
  return [c];
}

/** Contas a receber (cobranças) e a pagar. No modo API, só as cobranças emitidas. */
export async function listarFaturas(direcao?: Fatura["direcao"]): Promise<Fatura[]> {
  await delay(350);
  if (MODO_API) {
    if (direcao === "pagar") return [];
    const cobs = await get<CobrancaApi[]>("/cobrancas?limite=100");
    return cobs
      .filter((c) => c.status === "aberta" || c.status === "paga")
      .map((c) => {
        const imposto = c.vai_reter_imposto ? num(c.cbs) + num(c.ibs) : 0;
        return {
          id: c.id,
          direcao: "receber" as const,
          contraparte:
            c.descricao || (c.pagador_documento ? `Doc. ${c.pagador_documento}` : "Cliente"),
          nf: c.nfe_chave ? `NF-e …${c.nfe_chave.slice(-8)}` : "Sem nota",
          valor_bruto: num(c.valor),
          imposto,
          liquido: r2(num(c.valor) - imposto),
          credito_gerado: 0,
          vencimento: c.vencimento ?? new Date().toISOString(),
          status: c.status === "paga" ? ("liquidado" as const) : ("pendente" as const),
        };
      });
  }
  const criadas: Fatura[] = minhasCobrancasDemo().map((c) => {
    const imposto = c.vai_reter_imposto ? c.cbs + c.ibs : 0;
    return {
      id: c.id,
      direcao: "receber",
      contraparte: c.descricao || "Cliente",
      nf: c.nfe_chave ? `NF-e …${c.nfe_chave.slice(-8)}` : "Sem nota",
      valor_bruto: c.valor,
      imposto,
      liquido: r2(c.valor - imposto),
      credito_gerado: 0,
      vencimento: c.vencimento ?? new Date().toISOString(),
      status: "pendente",
    };
  });
  return [...(ehContaDoRoteiro() ? faturas : []), ...criadas]
    .filter((f) => !direcao || f.direcao === direcao)
    .sort((a, b) => a.vencimento.localeCompare(b.vencimento));
}

// =============================================================================
// Loja, Viagens e pontos (benefícios PF)
// =============================================================================

interface ProdutoApi extends Omit<Produto, "preco"> {
  preco: string;
}
interface VooApi extends Omit<Voo, "preco"> {
  preco: string;
}
interface CompraApi {
  transacao: TransacaoApi;
  pontos_ganhos: number;
  saldo_pontos: number;
}

/** Comprar em reais rende 1 ponto por real (Loja e Viagens). */
export const pontosDaCompra = (valor: number) => Math.floor(valor);

export async function listarProdutos(): Promise<Produto[]> {
  await delay(350);
  if (MODO_API)
    return (await get<ProdutoApi[]>("/loja/produtos")).map((p) => ({ ...p, preco: num(p.preco) }));
  return [...PRODUTOS];
}

export async function produtoPorId(id: number): Promise<Produto> {
  await delay(200);
  if (MODO_API) {
    const p = await get<ProdutoApi>(`/loja/produtos/${id}`);
    return { ...p, preco: num(p.preco) };
  }
  const p = PRODUTOS.find((x) => x.id === id);
  if (!p) throw new ApiError("Produto não encontrado.", 404);
  return { ...p };
}

async function compraApi(caminho: string, biometria?: ProvaBiometrica | null): Promise<Transacao> {
  const r = await post<CompraApi>(caminho, biometria ? { biometria } : {});
  return { ...mapTransacao(r.transacao, r.transacao.origem.carteira_id), categoria: "compra" };
}

export async function comprarProduto(p: ComprarProdutoPayload): Promise<Transacao> {
  await delay(800);
  if (MODO_API) return compraApi(`/loja/produtos/${p.produto_id}/comprar`, p.biometria);
  if (sessao.conta.tipo !== "PF")
    throw new ApiError("A Loja é exclusiva para contas Pessoa Física.", 403);
  const produto = await produtoPorId(p.produto_id);
  const destino = await consultarDestino(String(produto.merchant_carteira_id));
  const t = registrarPagamento({
    destino,
    valor: produto.preco,
    comBiometria: Boolean(p.biometria),
    categoria: "compra",
    descricao: `${produto.merchant_nome} · ${produto.nome}`,
  });
  sessao.conta.pontos += pontosDaCompra(produto.preco);
  persistirSessao();
  await aguardarEnvio();
  return t;
}

export async function buscarVoos(origem?: string, destino?: string): Promise<Voo[]> {
  await delay(400);
  if (MODO_API) {
    const q = new URLSearchParams();
    if (origem) q.set("origem", origem);
    if (destino) q.set("destino", destino);
    return (await get<VooApi[]>(`/viagens/voos?${q.toString()}`)).map((v) => ({
      ...v,
      preco: num(v.preco),
    }));
  }
  return VOOS.filter(
    (v) => (!origem || v.origem === origem) && (!destino || v.destino === destino),
  );
}

export async function vooPorId(id: number): Promise<Voo> {
  await delay(200);
  if (MODO_API) {
    const v = await get<VooApi>(`/viagens/voos/${id}`);
    return { ...v, preco: num(v.preco) };
  }
  const v = VOOS.find((x) => x.id === id);
  if (!v) throw new ApiError("Voo não encontrado.", 404);
  return { ...v };
}

/** Passagem paga em reais (rende 1 ponto por real). */
export async function comprarPassagem(p: ComprarPassagemPayload): Promise<Transacao> {
  await delay(900);
  if (MODO_API) {
    const t = await compraApi(`/viagens/voos/${p.voo_id}/comprar`, p.biometria);
    return { ...t, categoria: "viagem" };
  }
  if (sessao.conta.tipo !== "PF")
    throw new ApiError("Viagens é um benefício das contas Pessoa Física.", 403);
  const voo = await vooPorId(p.voo_id);
  const destino = await consultarDestino(String(voo.merchant_carteira_id));
  const t = registrarPagamento({
    destino,
    valor: voo.preco,
    comBiometria: Boolean(p.biometria),
    categoria: "viagem",
    descricao: `Voo ${voo.origem} → ${voo.destino} · ${voo.companhia}`,
  });
  sessao.conta.pontos += pontosDaCompra(voo.preco);
  persistirSessao();
  await aguardarEnvio();
  return t;
}

export interface Resgate {
  localizador: string;
  voo: Voo;
  pontos_usados: number;
  saldo_pontos: number;
}

/** Passagem com pontos: debita `milhas` pontos, sem tocar no saldo em reais. */
export async function resgatarPassagem(vooId: number): Promise<Resgate> {
  await delay(900);
  if (MODO_API) {
    const r = await post<Omit<Resgate, "voo"> & { voo: VooApi }>(`/viagens/voos/${vooId}/resgatar`);
    return { ...r, voo: { ...r.voo, preco: num(r.voo.preco) } };
  }
  if (sessao.conta.tipo !== "PF")
    throw new ApiError("Viagens é um benefício das contas Pessoa Física.", 403);
  await sincronizar();
  const voo = await vooPorId(vooId);
  if (sessao.conta.pontos < voo.milhas)
    throw new ApiError(
      `Pontos insuficientes: este voo custa ${voo.milhas.toLocaleString("pt-BR")} pontos.`,
    );
  sessao.conta.pontos -= voo.milhas;
  persistirSessao();
  await aguardarEnvio();
  return {
    localizador: crypto.randomUUID().slice(0, 6).toUpperCase(),
    voo,
    pontos_usados: voo.milhas,
    saldo_pontos: sessao.conta.pontos,
  };
}

// =============================================================================
// Cartão virtual (só modo demonstração — tabela existe no backend, endpoints não)
// =============================================================================

export async function meuCartao(): Promise<Cartao> {
  await delay(300);
  const minha = sessao.conta.carteira_id;
  let c = cartoes.find((x) => x.carteira_id === minha);
  if (!c) {
    c = {
      id: genId(),
      carteira_id: minha,
      apelido: sessao.conta.tipo === "PJ" ? "Cartão corporativo virtual" : "Cartão virtual",
      numero_masc: `•••• •••• •••• ${1000 + (minha % 9000)}`,
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
  return { ...c };
}

export async function atualizarCartao(
  patch: Partial<Pick<Cartao, "estado" | "compras_online" | "compras_internacionais">>,
): Promise<Cartao> {
  await delay(350);
  const c = cartoes.find((x) => x.carteira_id === sessao.conta.carteira_id);
  if (!c) throw new ApiError("Cartão não encontrado.", 404);
  Object.assign(c, patch);
  return { ...c };
}

export async function cvvDinamico(): Promise<CvvDinamico> {
  await delay(200);
  const cvv = String(Math.floor(100 + Math.random() * 900));
  return { cvv, expira_em: Date.now() + 60_000 };
}

// =============================================================================
// Central de notificações, equipe (vínculos) e aprovações pendentes
// Front primeiro: estes recursos ainda não têm endpoint no backend; por ora
// operam sobre os mocks em ambos os modos.
// =============================================================================

const notificacoesNovas = new Map<number, Notificacao[]>();
const equipesNovas = new Map<number, MembroEquipe[]>();

function listaNotificacoes(): Notificacao[] {
  if (ehContaDoRoteiro()) return sessao.conta.tipo === "PJ" ? notificacoesPJ : notificacoesPF;
  const id = sessao.conta.carteira_id;
  let lista = notificacoesNovas.get(id);
  if (!lista) {
    lista = [
      {
        id: genId(),
        tipo: "sistema",
        titulo: "Boas-vindas à Astro",
        texto:
          sessao.conta.tipo === "PJ"
            ? "A conta da empresa está pronta. Cadastre o CNPJ como chave Pix e emita a primeira cobrança com nota."
            : "Sua conta está pronta. Cadastre uma chave Pix para começar a receber.",
        criado_em: new Date().toISOString(),
        lida: false,
      },
    ];
    notificacoesNovas.set(id, lista);
  }
  return lista;
}

function listaEquipe(): MembroEquipe[] {
  if (ehContaDoRoteiro()) return equipeDemo;
  const id = sessao.conta.carteira_id;
  let lista = equipesNovas.get(id);
  if (!lista) {
    const dono = donoDaConta(id);
    lista = dono
      ? [
          {
            id: genId(),
            nome: dono.nome,
            email: dono.email,
            papel: "admin",
            alcada: null,
            status: "ativo",
            ativo: true,
            eu: true,
          },
        ]
      : [];
    equipesNovas.set(id, lista);
  }
  return lista;
}

export async function notificacoes(): Promise<Notificacao[]> {
  await delay(250);
  return [...listaNotificacoes()].sort((a, b) => b.criado_em.localeCompare(a.criado_em));
}

export async function naoLidas(): Promise<number> {
  return listaNotificacoes().filter((n) => !n.lida).length;
}

export async function marcarNotificacoesLidas(): Promise<void> {
  await delay(150);
  listaNotificacoes().forEach((n) => {
    n.lida = true;
  });
}

// =============================================================================
// Equipe da empresa (vínculos por CPF), convites recebidos e aprovações
// =============================================================================

interface VinculoApi {
  id: number;
  nome: string | null;
  email: string | null;
  cpf: string | null;
  cargo: string | null;
  papel: MembroEquipe["papel"];
  alcada: string | null;
  status: MembroEquipe["status"];
  ativo: boolean;
  ultimo_acesso_em: string | null;
  eu: boolean;
}

function mapVinculo(v: VinculoApi): MembroEquipe {
  return {
    id: v.id,
    nome: v.nome ?? "Pessoa convidada",
    email: v.email,
    cpf: v.cpf,
    cargo: v.cargo,
    papel: v.papel,
    alcada: v.alcada == null ? null : num(v.alcada),
    status: v.status,
    ativo: v.ativo,
    ultimo_acesso_em: v.ultimo_acesso_em,
    eu: v.eu,
  };
}

export async function equipe(): Promise<MembroEquipe[]> {
  await delay(300);
  if (MODO_API) return (await get<VinculoApi[]>("/empresas/atual/vinculos")).map(mapVinculo);
  return [...listaEquipe()];
}

export async function politicaEmpresa(): Promise<PoliticaEmpresa> {
  if (MODO_API) {
    const p = await get<
      Omit<PoliticaEmpresa, "duas_aprovacoes_acima"> & { duas_aprovacoes_acima: string | null }
    >("/empresas/atual/politica");
    return {
      ...p,
      duas_aprovacoes_acima: p.duas_aprovacoes_acima == null ? null : num(p.duas_aprovacoes_acima),
    };
  }
  const porte = sessao.conta.porte ?? "PME";
  return {
    porte,
    max_usuarios: porte === "MEI" ? 3 : porte === "GRANDE" ? 500 : 30,
    papeis_convidaveis:
      porte === "MEI" ? ["operador", "consulta"] : ["admin", "aprovador", "operador", "consulta"],
    operador_exige_alcada: porte !== "PME",
    quatro_olhos_acesso: porte === "GRANDE",
    duas_aprovacoes_acima: porte === "GRANDE" ? 250000 : null,
    resumo:
      porte === "MEI"
        ? "Dono único: só o titular administra. Acesso extra só como operador (com alçada) ou consulta."
        : porte === "GRANDE"
          ? "Quatro olhos em pagamentos e na gestão de acesso; operador sempre com alçada; valores altos exigem duas aprovações."
          : "Vários usuários; acima da alçada outra pessoa aprova; dar poder exige o rosto de quem concede.",
    usuarios_ocupados: listaEquipe().filter((m) => m.status !== "revogado").length,
  };
}

/** O admin convida uma PESSOA pelo CPF; ela aceita com o próprio login e rosto. */
export async function convidarMembro(p: ConvidarPayload): Promise<MembroEquipe> {
  await delay(500);
  if (MODO_API)
    return mapVinculo(
      await post<VinculoApi>("/empresas/atual/vinculos", {
        nome: p.nome,
        cpf: p.cpf,
        papel: p.papel,
        alcada: p.alcada == null ? null : p.alcada.toFixed(2),
        ...(p.email ? { email: p.email } : {}),
        ...(p.cargo ? { cargo: p.cargo } : {}),
        ...(p.biometria ? { biometria: p.biometria } : {}),
      }),
    );
  const dig = p.cpf.replace(/\D/g, "");
  const novo: MembroEquipe = {
    id: genId(),
    nome: p.nome,
    email: p.email ?? null,
    cpf: `***.${dig.slice(3, 6)}.${dig.slice(6, 9)}-**`,
    papel: p.papel,
    alcada: p.alcada,
    status: "pendente",
    ativo: false,
  };
  listaEquipe().push(novo);
  return novo;
}

export type AcaoMembro = "suspender" | "reativar" | "revogar";

export async function mudarAcessoMembro(
  id: number,
  acao: AcaoMembro,
  biometria?: ProvaBiometrica,
): Promise<MembroEquipe> {
  await delay(400);
  if (MODO_API) {
    if (acao === "revogar")
      return mapVinculo(await del<VinculoApi>(`/empresas/atual/vinculos/${id}`));
    return mapVinculo(
      await post<VinculoApi>(
        `/empresas/atual/vinculos/${id}/${acao}`,
        acao === "reativar" ? { biometria: biometria ?? null } : undefined,
      ),
    );
  }
  const m = listaEquipe().find((x) => x.id === id);
  if (!m) throw new ApiError("Pessoa não encontrada nesta empresa.", 404);
  if (m.eu) throw new ApiError("A empresa precisa de pelo menos um administrador ativo.");
  m.status = acao === "suspender" ? "suspenso" : acao === "revogar" ? "revogado" : "ativo";
  m.ativo = m.status === "ativo";
  return { ...m };
}

export async function meusConvites(): Promise<ConviteRecebido[]> {
  if (!MODO_API) return [];
  const lista =
    await get<(VinculoApi & { empresa: { nome: string }; convidado_por: string | null })[]>(
      "/convites",
    );
  return lista.map((c) => ({
    id: c.id,
    empresa: c.empresa.nome,
    papel: c.papel,
    alcada: c.alcada == null ? null : num(c.alcada),
    convidado_por: c.convidado_por,
  }));
}

/** Aceitar exige o rosto de quem foi convidado (e o KYC dela concluído). */
export async function aceitarConvite(id: number, biometria: ProvaBiometrica): Promise<Conta[]> {
  await post(`/convites/${id}/aceitar`, { biometria });
  return (await contasDaPessoa()).contas;
}

export async function recusarConvite(id: number): Promise<void> {
  await post(`/convites/${id}/recusar`);
}

interface PendenteApi {
  id: number;
  tipo: TipoPendente;
  valor: string;
  descricao: string | null;
  status: "pendente" | "aprovada" | "rejeitada" | "falhou";
  criado_por_nome?: string;
  criado_em: string;
  aprovacoes_necessarias: number;
  aprovacoes: { usuario_id: number; nome: string }[];
}

const TIPO_PENDENTE: Record<TipoPendente, string> = {
  transferencia: "Transferência",
  pagamento_cobranca: "Pagamento de cobrança",
  folha: "Folha de pagamento",
  acesso: "Acesso à conta",
};

function mapPendente(p: PendenteApi): OperacaoPendente {
  return {
    id: p.id,
    tipo: p.tipo,
    descricao: p.descricao ?? TIPO_PENDENTE[p.tipo],
    contraparte: TIPO_PENDENTE[p.tipo] ?? p.tipo,
    valor: num(p.valor),
    criado_por: p.criado_por_nome ?? "—",
    criado_em: p.criado_em,
    status:
      p.status === "pendente" ? "aguardando" : p.status === "aprovada" ? "aprovada" : "recusada",
    aprovacoes_necessarias: p.aprovacoes_necessarias,
    aprovadores: p.aprovacoes.map((a) => a.nome),
  };
}

export async function pendentes(): Promise<OperacaoPendente[]> {
  await delay(300);
  if (MODO_API) {
    const listas = await Promise.all(
      ["pendente", "aprovada", "rejeitada"].map((st) =>
        get<PendenteApi[]>(`/empresas/atual/pendentes?status=${st}`),
      ),
    );
    return listas
      .flat()
      .map(mapPendente)
      .sort((a, b) => b.criado_em.localeCompare(a.criado_em));
  }
  return (ehContaDoRoteiro() ? [...pendentesDemo] : []).sort((a, b) =>
    b.criado_em.localeCompare(a.criado_em),
  );
}

/** Rosto de quem aprova: exigido acima do limite facial e em mudança de acesso. */
export function aprovacaoPedeRosto(o: OperacaoPendente): boolean {
  return o.tipo === "acesso" || o.valor > LIMITE_SELFIE;
}

export async function decidirPendente(
  id: number,
  aprovar: boolean,
  biometria?: ProvaBiometrica,
): Promise<OperacaoPendente & { mensagem?: string }> {
  await delay(600);
  if (MODO_API) {
    const r = await post<PendenteApi & { mensagem?: string }>(
      `/pagamentos/pendentes/${id}/decidir`,
      { aprovar, ...(biometria ? { biometria } : {}) },
    );
    return { ...mapPendente(r), ...(r.mensagem ? { mensagem: r.mensagem } : {}) };
  }
  const op = pendentesDemo.find((o) => o.id === id);
  if (!op) throw new ApiError("Operação não encontrada.", 404);
  op.status = aprovar ? "aprovada" : "recusada";
  return { ...op };
}

export { VIGENCIA_ATUAL };
