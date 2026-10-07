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
  dispositivoId,
  get,
  MODO_API,
  num,
  post,
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
  ComprarProdutoPayload,
  Conta,
  CvvDinamico,
  DepositarPayload,
  Desafio,
  DestinoRef,
  Fatura,
  Limites,
  LoginPayload,
  LoginResposta,
  MembroEquipe,
  Notificacao,
  OperacaoPendente,
  Produto,
  ProvaBiometrica,
  RegistrarPayload,
  ResultadoTransferencia,
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
  if (!MODO_API) sessao.conta = { ...conta };
}

async function contasDaPessoa(): Promise<Conta[]> {
  const eu = await get<{ contas: ContaApi[] }>("/auth/eu");
  return eu.contas.map(mapConta);
}

export async function login({ email, senha }: LoginPayload): Promise<LoginResposta> {
  await delay();
  if (!email || !senha) throw new ApiError("Informe e-mail (ou CPF) e senha.", 401);
  if (MODO_API) {
    definirConta(null);
    const tk = await post<{ access_token: string; refresh_token: string }>("/auth/login", {
      email,
      senha,
    });
    salvarTokens(tk);
    const contas = await contasDaPessoa();
    const conta = contas.find((c) => c.tipo === "PF") ?? contas[0];
    if (!conta) throw new ApiError("Esta pessoa não tem nenhuma conta para operar.", 404);
    selecionarConta(conta);
    return { contas, conta };
  }
  // Demonstração: a mesma pessoa opera a conta pessoal e a empresa.
  const contas = [{ ...contasDemo.PF }, { ...contasDemo.PJ }];
  selecionarConta(contas[0]!);
  return { contas, conta: contas[0]! };
}

/** Entrar com o rosto: o desafio é pedido para este login e conferido no servidor. */
export async function loginBiometria(
  identificador: string,
  prova: ProvaBiometrica,
): Promise<LoginResposta> {
  await delay();
  if (MODO_API) {
    definirConta(null);
    const tk = await post<{ access_token: string; refresh_token: string }>(
      "/auth/login/biometria",
      {
        email: identificador,
        biometria: prova,
      },
    );
    salvarTokens(tk);
    const contas = await contasDaPessoa();
    const conta = contas.find((c) => c.tipo === "PF") ?? contas[0];
    if (!conta) throw new ApiError("Esta pessoa não tem nenhuma conta para operar.", 404);
    selecionarConta(conta);
    return { contas, conta };
  }
  return login({ email: identificador, senha: "biometria" });
}

export async function registrar(p: RegistrarPayload): Promise<LoginResposta> {
  await delay(700);
  if (p.senha.length < 8) throw new ApiError("A senha precisa ter ao menos 8 caracteres.");
  if (MODO_API) {
    await post("/usuarios", {
      nome: p.nome,
      email: p.email,
      senha: p.senha,
      cpf: p.cpf,
      biometria: p.biometria,
    });
    const r = await login({ email: p.email, senha: p.senha });
    if (!p.empresa) return r;
    const pj = mapConta(await post<ContaApi>("/empresas", p.empresa));
    if (p.empresa.setor) pj.setor = p.empresa.setor;
    return { contas: [...r.contas, pj], conta: r.conta };
  }
  const id = genId();
  const pf: Conta = {
    id,
    nome: p.nome,
    tipo: "PF",
    carteira_id: 4000 + id,
    numero: `${4000 + id}`,
    saldo: 0,
    pontos: 0,
  };
  carteiras.push({ carteira_id: pf.carteira_id, nome: pf.nome, tipo: "PF" });
  const contas: Conta[] = [pf];
  if (p.empresa) {
    const pj: Conta = {
      id: id + 1,
      nome: p.empresa.nome_fantasia || `Empresa ${p.empresa.cnpj}`,
      tipo: "PJ",
      carteira_id: 5000 + id,
      numero: `${5000 + id}`,
      saldo: 0,
      pontos: 0,
      porte: p.empresa.porte,
      regime_apuracao: p.empresa.regime_apuracao,
      ...(p.empresa.setor ? { setor: p.empresa.setor } : {}),
      papel: "admin",
      alcada: null,
      creditos: 0,
    };
    carteiras.push({ carteira_id: pj.carteira_id, nome: pj.nome, tipo: "PJ" });
    contas.push(pj);
  }
  selecionarConta(pf);
  return { contas, conta: pf };
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

export async function pedirDesafio(login?: string): Promise<Desafio> {
  if (MODO_API) return post<Desafio>("/biometria/desafios", login ? { login } : {});
  const acao = Math.random() > 0.5 ? "virar_esquerda" : "virar_direita";
  return {
    desafio_id: `demo-${Date.now()}`,
    acao,
    instrucao:
      acao === "virar_esquerda" ? "Vire o rosto para a esquerda" : "Vire o rosto para a direita",
  };
}

// =============================================================================
// Conta e extrato
// =============================================================================

export async function minhaConta(): Promise<Conta> {
  await delay(250);
  if (MODO_API) {
    const c = mapConta(await get<ContaApi>("/contas/atual"));
    if (c.tipo === "PF") c.pontos = (await get<{ saldo: number }>("/pontos")).saldo;
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
  return { ...sessao.conta };
}

export async function transacoes_(): Promise<Transacao[]> {
  await delay(350);
  if (MODO_API) {
    const c = await get<ContaApi>("/contas/atual");
    const ts = await get<TransacaoApi[]>("/pagamentos/transacoes?limite=100");
    return ts.map((t) => mapTransacao(t, c.carteira_id));
  }
  const minha = sessao.conta.carteira_id;
  return transacoes
    .filter((t) => t.origem_carteira_id === minha || t.destino_carteira_id === minha)
    .sort((a, b) => b.criado_em.localeCompare(a.criado_em));
}
export { transacoes_ as transacoes };

export async function transacaoPorId(id: number): Promise<Transacao> {
  await delay(200);
  if (MODO_API) {
    const c = await get<ContaApi>("/contas/atual");
    return mapTransacao(await get<TransacaoApi>(`/pagamentos/transacoes/${id}`), c.carteira_id);
  }
  const t = transacoes.find((x) => x.id === id);
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
  const id = Number(alvo.replace(/\D/g, ""));
  const c = carteiras.find((x) => x.carteira_id === id);
  if (!c) throw new ApiError("Chave ou conta não encontrada.", 404);
  return { ...c, destino: { numero: String(c.carteira_id) } };
}

export async function simularSplit(
  valor: number,
  tipo_destino: TipoConta,
): Promise<SplitResultado> {
  return calcularSplit(valor, tipo_destino);
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
  transacoes.push(t);
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
  return { tipo: "transacao", transacao: t };
}

/** Depósito: no modo API o dinheiro entra por Pix para uma chave sua (ou pelo admin). */
export async function depositar(p: DepositarPayload): Promise<Transacao> {
  await delay(600);
  if (MODO_API)
    throw new ApiError(
      "Para colocar dinheiro, faça um Pix para uma das suas chaves. O depósito direto é só para a equipe (admin).",
      403,
    );
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
    status: "concluida",
    categoria: "deposito",
    descricao: "Depósito via Pix",
    criado_em: new Date().toISOString(),
  };
  sessao.conta.saldo = r2(sessao.conta.saldo + p.valor);
  transacoes.push(t);
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
  return [{ id: 1, tipo: "aleatoria", valor: "b1e2c3d4-0000-4000-8000-000000000000" }];
}

export async function criarChave(tipo: string, valor?: string): Promise<ChavePix> {
  if (MODO_API) return post<ChavePix>("/pix/chaves", { tipo, valor });
  return { id: genId(), tipo, valor: valor ?? crypto.randomUUID() };
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
  return { ...apuracaoDemo };
}

export async function listarCobrancas(): Promise<Cobranca[]> {
  await delay(300);
  if (MODO_API) return (await get<CobrancaApi[]>("/cobrancas?limite=100")).map(mapCobranca);
  return [...cobrancasDemo].sort((a, b) => b.id - a.id);
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
  const criadas: Fatura[] = cobrancasDemo.map((c) => {
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
  return [...faturas, ...criadas]
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
  const voo = await vooPorId(vooId);
  if (sessao.conta.pontos < voo.milhas)
    throw new ApiError(
      `Pontos insuficientes: este voo custa ${voo.milhas.toLocaleString("pt-BR")} pontos.`,
    );
  sessao.conta.pontos -= voo.milhas;
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

function listaNotificacoes(): Notificacao[] {
  return sessao.conta.tipo === "PJ" ? notificacoesPJ : notificacoesPF;
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

export async function equipe(): Promise<MembroEquipe[]> {
  await delay(300);
  return [...equipeDemo];
}

export async function convidarMembro(p: {
  nome: string;
  email: string;
  papel: MembroEquipe["papel"];
  alcada: number | null;
}): Promise<MembroEquipe> {
  await delay(500);
  const novo: MembroEquipe = {
    id: genId(),
    nome: p.nome,
    email: p.email,
    papel: p.papel,
    alcada: p.alcada,
    ativo: true,
  };
  equipeDemo.push(novo);
  return novo;
}

export async function pendentes(): Promise<OperacaoPendente[]> {
  await delay(300);
  return [...pendentesDemo].sort((a, b) => b.criado_em.localeCompare(a.criado_em));
}

export async function decidirPendente(id: number, aprovar: boolean): Promise<OperacaoPendente> {
  await delay(600);
  const op = pendentesDemo.find((o) => o.id === id);
  if (!op) throw new ApiError("Operação não encontrada.", 404);
  op.status = aprovar ? "aprovada" : "recusada";
  return { ...op };
}

export { VIGENCIA_ATUAL };
