/**
 * Cliente HTTP do backend Astro (FastAPI v7).
 *
 * - Ligado quando `VITE_API_URL` está definida (ex.: http://localhost:8000).
 *   Sem ela, o app roda no modo demonstração (mocks em src/mocks/data.ts).
 * - Manda sempre: `Authorization: Bearer`, `X-Dispositivo-Id` (id fixo deste
 *   aparelho, guardado no localStorage) e `X-Conta` (conta em uso — PF ou a PJ
 *   escolhida no seletor).
 * - Manda também `DPoP`: prova assinada pela chave não exportável deste aparelho
 *   (src/lib/dpop.ts). O servidor só aceita o token junto com essa prova.
 * - Em 401 de sessão (o servidor manda `WWW-Authenticate`; 401 de biometria não
 *   manda) tenta renovar uma vez com o refresh token (uma renovação por vez: duas
 *   em paralelo com o mesmo refresh seriam vistas como reuso e o servidor
 *   derrubaria a sessão). Se a sessão não volta (tempo máximo, inatividade,
 *   encerrada em outro aparelho...), limpa tudo e avisa `aoExpirarSessao`: o app
 *   vai para o login mostrando o motivo que o servidor deu.
 * - Dinheiro vem como string ("1500.00"); quem converte para número (só para
 *   exibir) é api.ts via `num()`. Nenhuma conta de dinheiro é feita no app.
 */

import { criarProva } from "./dpop";
import { Capacitor } from "@capacitor/core";

export const API_URL: string | undefined =
  (import.meta.env["VITE_API_URL"] as string | undefined)?.replace(/\/$/, "") || undefined;
export const MODO_API = Boolean(API_URL);

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}

const K_TOKENS = "payflow-tokens";
const K_CONTA = "payflow-conta-numero";
const K_DISPOSITIVO = "payflow-dispositivo";
const K_MOTIVO = "astro-motivo-saida";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

function ler<T>(storage: () => Storage, chave: string): T | null {
  try {
    const raw = storage().getItem(chave);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function gravar(storage: () => Storage, chave: string, valor: unknown) {
  try {
    if (valor === null) storage().removeItem(chave);
    else storage().setItem(chave, JSON.stringify(valor));
  } catch {
    /* storage indisponível (modo privado) — segue só em memória */
  }
}

const sess = () => window.sessionStorage;
const local = () => window.localStorage;

let tokens: Tokens | null =
  typeof window !== "undefined" && !Capacitor.isNativePlatform()
    ? ler<Tokens>(sess, K_TOKENS)
    : null;
let contaNumero: string | null =
  typeof window !== "undefined" && !Capacitor.isNativePlatform()
    ? ler<string>(sess, K_CONTA)
    : null;
if (typeof window !== "undefined" && Capacitor.isNativePlatform()) {
  gravar(sess, K_TOKENS, null);
  gravar(sess, K_CONTA, null);
}
/**
 * Muda quando a IDENTIDADE da sessão muda (login, logout, queda). Resposta que chega
 * depois disso é de outra sessão e é descartada. A rotação do refresh NÃO muda a versão:
 * é a mesma sessão, e descartar a resposta de um Pix já executado levaria a pessoa a
 * repetir o pagamento.
 */
let versaoSessao = 0;

export function salvarTokens(
  t: Tokens | null,
  { renovacao = false }: { renovacao?: boolean } = {},
) {
  if (!renovacao) versaoSessao++;
  tokens = t;
  gravar(sess, K_TOKENS, Capacitor.isNativePlatform() ? null : t);
}

/** Permite encerrar também a sessão mantida só em memória (storage indisponível). */
export function refreshDaSessao(): string | undefined {
  return tokens?.refresh_token;
}

export function definirConta(numero: string | null) {
  contaNumero = numero;
  gravar(sess, K_CONTA, Capacitor.isNativePlatform() ? null : numero);
}

/** Id estável deste aparelho (o backend guarda só o hash). */
export function dispositivoId(): string {
  let id = typeof window !== "undefined" ? ler<string>(local, K_DISPOSITIVO) : null;
  if (!id) {
    id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    gravar(local, K_DISPOSITIVO, id);
  }
  return id;
}

export const num = (v: string | number | null | undefined): number => (v == null ? 0 : Number(v));

// --- Sessão encerrada pelo servidor -----------------------------------------

type Ouvinte = (motivo: string) => void;
const ouvintes = new Set<Ouvinte>();

/** Chamado quando o servidor recusa a sessão e ela não pôde ser renovada. */
export function aoExpirarSessao(fn: Ouvinte): () => void {
  ouvintes.add(fn);
  return () => ouvintes.delete(fn);
}

function encerrarSessao(motivo: string) {
  salvarTokens(null);
  definirConta(null);
  gravar(sess, K_MOTIVO, motivo);
  ouvintes.forEach((fn) => fn(motivo));
}

/** Motivo da última queda de sessão (lido uma vez pela tela de login). */
export function motivoSaida(): string | null {
  if (typeof window === "undefined") return null;
  const m = ler<string>(sess, K_MOTIVO);
  gravar(sess, K_MOTIVO, null);
  return m;
}

/** Rotas de entrada/saída: um 401 nelas não é "sessão caiu". */
const ROTA_DE_ENTRADA = /^\/auth\/(login|refresh|logout|recuperacao)(\/|$)/;

function detalheDe(dados: unknown): string | null {
  const d = (dados as { detail?: unknown } | null)?.detail;
  return typeof d === "string" ? d : null;
}

// --- Renovação ---------------------------------------------------------------

/** ok = renovou; recusada = o servidor encerrou a sessão; falhou = erro passageiro. */
type Renovacao = { ok: true } | { ok: false; recusada: boolean; motivo: string };

let renovando: Promise<Renovacao> | null = null;

async function renovarAgora(): Promise<Renovacao> {
  const versao = versaoSessao;
  const refresh = tokens?.refresh_token;
  if (!refresh) return { ok: false, recusada: true, motivo: "Sua sessão terminou. Entre de novo." };
  // A sessão é presa ao aparelho: o refresh só vale com a mesma chave (DPoP).
  const url = `${API_URL}/auth/refresh`;
  let r: Response;
  try {
    r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Dispositivo-Id": dispositivoId(),
        DPoP: await criarProva("POST", url),
      },
      body: JSON.stringify({ refresh_token: refresh }),
    });
  } catch {
    return { ok: false, recusada: false, motivo: "Sem conexão com o servidor." };
  }
  if (versao !== versaoSessao) return { ok: false, recusada: false, motivo: "A sessão mudou." };
  if (!r.ok) {
    const motivo =
      detalheDe(await r.json().catch(() => null)) ?? "Sua sessão terminou. Entre de novo.";
    if (versao !== versaoSessao) return { ok: false, recusada: false, motivo: "A sessão mudou." };
    // 429/5xx: a sessão continua válida, só não deu para renovar agora.
    return { ok: false, recusada: r.status === 401 || r.status === 403, motivo };
  }
  const novos = (await r.json()) as Tokens;
  if (versao !== versaoSessao) return { ok: false, recusada: false, motivo: "A sessão mudou." };
  salvarTokens(novos, { renovacao: true });
  return { ok: true };
}

function renovar(): Promise<Renovacao> {
  renovando ??= renovarAgora().finally(() => {
    renovando = null;
  });
  return renovando;
}

export interface Resposta<T> {
  status: number;
  dados: T;
}

export async function requisitar<T>(
  metodo: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  caminho: string,
  corpo?: unknown,
  tentouRenovar = false,
  anonimo = false,
): Promise<Resposta<T>> {
  if (!API_URL) throw new ApiError("Backend não configurado (VITE_API_URL).", 500);
  const versao = versaoSessao;
  const headers: Record<string, string> = { "X-Dispositivo-Id": dispositivoId() };
  if (corpo !== undefined) headers["Content-Type"] = "application/json";
  if (!anonimo && tokens?.access_token) headers["Authorization"] = `Bearer ${tokens.access_token}`;
  if (!anonimo && contaNumero) headers["X-Conta"] = contaNumero;
  const url = `${API_URL}${caminho}`;
  if (!anonimo) headers["DPoP"] = await criarProva(metodo, url, tokens?.access_token);

  let r: Response;
  try {
    r = await fetch(url, {
      method: metodo,
      headers,
      body: corpo === undefined ? null : JSON.stringify(corpo),
    });
  } catch {
    throw new ApiError("Sem conexão com o servidor. Verifique a internet e tente de novo.", 0);
  }

  if (versao !== versaoSessao) throw new ApiError("A sessão mudou. Tente de novo.", 409);

  // 401 de sessão (token vencido, sessão encerrada, outra chave...). 401 de
  // biometria ("rosto não confere") não traz WWW-Authenticate e não derruba nada.
  const sessaoRecusada =
    r.status === 401 &&
    !anonimo &&
    r.headers.has("WWW-Authenticate") &&
    !ROTA_DE_ENTRADA.test(caminho);
  let motivoQueda: string | null = null;
  if (sessaoRecusada && !tentouRenovar) {
    const rn = await renovar();
    if (rn.ok) return requisitar<T>(metodo, caminho, corpo, true);
    if (!rn.recusada)
      throw new ApiError("Não deu para confirmar sua sessão agora. Tente de novo.", 503);
    motivoQueda = rn.motivo;
  }
  const versaoResposta = versaoSessao;
  const texto = await r.text();
  if (versaoResposta !== versaoSessao) throw new ApiError("A sessão mudou. Tente de novo.", 409);
  const dados = texto ? (JSON.parse(texto) as unknown) : null;
  if (!r.ok) {
    const msg =
      detalheDe(dados) ??
      (Array.isArray((dados as { detail?: unknown } | null)?.detail)
        ? "Dados inválidos: confira os campos."
        : `Erro ${r.status}`);
    if (sessaoRecusada) encerrarSessao(motivoQueda ?? msg);
    throw new ApiError(msg, r.status);
  }
  return { status: r.status, dados: dados as T };
}

export async function get<T>(caminho: string): Promise<T> {
  return (await requisitar<T>("GET", caminho)).dados;
}

export async function post<T>(caminho: string, corpo?: unknown): Promise<T> {
  return (await requisitar<T>("POST", caminho, corpo ?? {})).dados;
}

/** Sem credenciais, mesmo com alguém logado neste navegador (ex.: abrir outra conta). */
export async function postAnonimo<T>(caminho: string, corpo?: unknown): Promise<T> {
  return (await requisitar<T>("POST", caminho, corpo ?? {}, false, true)).dados;
}

export async function patch<T>(caminho: string, corpo: unknown): Promise<T> {
  return (await requisitar<T>("PATCH", caminho, corpo)).dados;
}

export async function del<T>(caminho: string): Promise<T> {
  return (await requisitar<T>("DELETE", caminho)).dados;
}
