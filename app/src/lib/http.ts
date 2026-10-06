/**
 * Cliente HTTP do backend PayFlow (FastAPI v7).
 *
 * - Ligado quando `VITE_API_URL` está definida (ex.: http://localhost:8000).
 *   Sem ela, o app roda no modo demonstração (mocks em src/mocks/data.ts).
 * - Manda sempre: `Authorization: Bearer`, `X-Dispositivo-Id` (id fixo deste
 *   aparelho, guardado no localStorage) e `X-Conta` (conta em uso — PF ou a PJ
 *   escolhida no seletor).
 * - Em 401 tenta renovar a sessão uma vez com o refresh token.
 * - Dinheiro vem como string ("1500.00"); quem converte para número (só para
 *   exibir) é api.ts via `num()`. Nenhuma conta de dinheiro é feita no app.
 */

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

let tokens: Tokens | null = typeof window !== "undefined" ? ler<Tokens>(sess, K_TOKENS) : null;
let contaNumero: string | null = typeof window !== "undefined" ? ler<string>(sess, K_CONTA) : null;

export function salvarTokens(t: Tokens | null) {
  tokens = t;
  gravar(sess, K_TOKENS, t);
}

export function definirConta(numero: string | null) {
  contaNumero = numero;
  gravar(sess, K_CONTA, numero);
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

async function renovar(): Promise<boolean> {
  if (!tokens?.refresh_token) return false;
  const r = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!r.ok) {
    salvarTokens(null);
    return false;
  }
  salvarTokens((await r.json()) as Tokens);
  return true;
}

export interface Resposta<T> {
  status: number;
  dados: T;
}

export async function requisitar<T>(
  metodo: "GET" | "POST" | "PUT" | "DELETE",
  caminho: string,
  corpo?: unknown,
  tentouRenovar = false,
): Promise<Resposta<T>> {
  if (!API_URL) throw new ApiError("Backend não configurado (VITE_API_URL).", 500);
  const headers: Record<string, string> = { "X-Dispositivo-Id": dispositivoId() };
  if (corpo !== undefined) headers["Content-Type"] = "application/json";
  if (tokens?.access_token) headers["Authorization"] = `Bearer ${tokens.access_token}`;
  if (contaNumero) headers["X-Conta"] = contaNumero;

  let r: Response;
  try {
    r = await fetch(`${API_URL}${caminho}`, {
      method: metodo,
      headers,
      body: corpo === undefined ? null : JSON.stringify(corpo),
    });
  } catch {
    throw new ApiError("Sem conexão com o servidor. Verifique a internet e tente de novo.", 0);
  }

  if (
    r.status === 401 &&
    !tentouRenovar &&
    tokens?.refresh_token &&
    !caminho.startsWith("/auth/")
  ) {
    if (await renovar()) return requisitar<T>(metodo, caminho, corpo, true);
  }
  const texto = await r.text();
  const dados = texto ? (JSON.parse(texto) as unknown) : null;
  if (!r.ok) {
    const detalhe = (dados as { detail?: unknown } | null)?.detail;
    const msg =
      typeof detalhe === "string"
        ? detalhe
        : Array.isArray(detalhe)
          ? "Dados inválidos: confira os campos."
          : `Erro ${r.status}`;
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
