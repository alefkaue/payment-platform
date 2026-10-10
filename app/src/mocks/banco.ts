/**
 * "Banco" do modo demonstração: pessoas cadastradas, contas (com saldo), chaves
 * Pix e transações novas, guardados no localStorage do navegador. Assim, no
 * mesmo navegador, uma pessoa cria a conta, cadastra chaves e recebe Pix de
 * outra conta — como no backend. Os dados NÃO são compartilhados entre
 * aparelhos, a não ser que o build tenha VITE_DEMO_SYNC_URL: aí o banco demo é
 * espelhado num JSON público (ex.: npoint.io) e celular e computador enxergam as
 * mesmas contas, chaves e Pix. Senhas vão só como hash (SHA-256).
 *
 * As regras de chave espelham backend/app/services/pix_service.py.
 */
import type { Conta, Transacao } from "@/lib/types";
import { contasDemo, reservarIds, transacoes as transacoesSemeadas } from "./data";

export interface PessoaDemo {
  nome: string;
  email: string;
  senha: string;
  cpf: string;
  contas: number[];
}

export interface ChaveDemo {
  id: number;
  carteira_id: number;
  tipo: "cpf" | "cnpj" | "email" | "celular" | "aleatoria";
  valor: string;
}

interface BancoDemo {
  versao: 1;
  pessoas: PessoaDemo[];
  contas: Record<string, Conta>;
  chaves: ChaveDemo[];
  transacoes: Transacao[];
  contestacoes?: { transacao_id: number; motivo: string; criado_em: string }[];
}

const KEY = "astro-demo-banco";
export const MAX_CHAVES = { PF: 5, PJ: 20 } as const;

// Pessoa da demonstração (a mesma do roteiro da apresentação).
export const MARINA: PessoaDemo = {
  nome: "Marina Alves",
  email: "marina@email.com",
  senha: "",
  cpf: "52998224725",
  contas: [contasDemo.PF.carteira_id, contasDemo.PJ.carteira_id],
};

function semente(): BancoDemo {
  return {
    versao: 1,
    pessoas: [MARINA],
    contas: {
      [contasDemo.PF.carteira_id]: { ...contasDemo.PF },
      [contasDemo.PJ.carteira_id]: { ...contasDemo.PJ },
    },
    chaves: [
      {
        id: 1,
        carteira_id: contasDemo.PF.carteira_id,
        tipo: "aleatoria",
        valor: "b1e2c3d4-0000-4000-8000-000000000000",
      },
      { id: 2, carteira_id: contasDemo.PF.carteira_id, tipo: "email", valor: MARINA.email },
      { id: 3, carteira_id: contasDemo.PJ.carteira_id, tipo: "cnpj", valor: "12345678000190" },
    ],
    transacoes: [],
  };
}

let memoria: BancoDemo | null = null;

// --- Sincronização entre aparelhos (opcional) ---------------------------------------
const SYNC = (import.meta.env["VITE_DEMO_SYNC_URL"] as string | undefined) || undefined;
let envio: Promise<void> | null = null;

/** Espera o último envio terminar (para o outro aparelho já ver a mudança). */
export async function aguardarEnvio(): Promise<void> {
  if (envio) await envio;
}

/** Traz o banco compartilhado para este aparelho (sem rede, segue com o local). */
export async function puxar(): Promise<void> {
  if (!SYNC || typeof window === "undefined") return;
  await aguardarEnvio(); // não sobrescreve uma mudança local ainda não enviada
  try {
    const r = await fetch(SYNC, { cache: "no-store" });
    if (!r.ok) return;
    const b = (await r.json()) as BancoDemo | null;
    if (b?.versao === 1) window.localStorage.setItem(KEY, JSON.stringify(b));
  } catch {
    /* offline: usa o que está no aparelho */
  }
}

function enviar(b: BancoDemo) {
  if (!SYNC) return;
  const corpo = JSON.stringify(b);
  const anterior = envio;
  envio = (async () => {
    if (anterior) await anterior;
    try {
      await fetch(SYNC, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: corpo,
      });
    } catch {
      /* offline: fica só neste aparelho */
    }
  })();
}

// --- Senha (no banco compartilhado nunca vai em texto) ------------------------------
async function sha256(txt: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(txt));
  return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

export async function hashSenha(email: string, senha: string): Promise<string> {
  return `sha256:${await sha256(`astro-demo:${email}:${senha}`)}`;
}

export async function senhaConfere(p: PessoaDemo, senha: string): Promise<boolean> {
  if (!p.senha) return true; // pessoa do roteiro: qualquer senha
  if (p.senha.startsWith("sha256:")) return p.senha === (await hashSenha(p.email, senha));
  return p.senha === senha;
}

/** Lê sempre do localStorage: outra aba (outra conta) pode ter mudado os dados. */
export function banco(): BancoDemo {
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) {
        const b = JSON.parse(raw) as BancoDemo;
        if (b?.versao === 1) {
          memoria = b;
          reservarIds(maiorId(b));
          return b;
        }
      }
      // Storage vazio (primeiro acesso ou "recomeçar" limpou): volta ao estado inicial.
      memoria = semente();
      return memoria;
    } catch {
      /* storage bloqueado: segue em memória */
    }
  }
  memoria ??= semente();
  return memoria;
}

export function salvar(b: BancoDemo) {
  memoria = b;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(b));
  } catch {
    /* sem storage: vale só até recarregar a página */
  }
  enviar(b);
}

function maiorId(b: BancoDemo): number {
  const ids = [
    ...b.transacoes.map((t) => t.id),
    ...b.chaves.map((k) => k.id),
    ...Object.values(b.contas).map((c) => c.id),
  ];
  return ids.length ? Math.max(...ids) : 0;
}

// --- Pessoas e contas ------------------------------------------------------------

const digitos = (s: string) => s.replace(/\D/g, "");

export function pessoaPorLogin(login: string): PessoaDemo | undefined {
  const l = login.trim().toLowerCase();
  const d = digitos(l);
  return banco().pessoas.find((p) => p.email === l || (d.length === 11 && p.cpf === d));
}

export function donoDaConta(carteira_id: number): PessoaDemo | undefined {
  return banco().pessoas.find((p) => p.contas.includes(carteira_id));
}

export function contasDa(p: PessoaDemo): Conta[] {
  const b = banco();
  return p.contas
    .map((id) => b.contas[id])
    .filter((c): c is Conta => Boolean(c))
    .map((c) => ({ ...c }));
}

export function contaPorId(carteira_id: number): Conta | undefined {
  const c = banco().contas[carteira_id];
  return c ? { ...c } : undefined;
}

export function guardarConta(c: Conta) {
  const b = banco();
  b.contas[c.carteira_id] = { ...c };
  salvar(b);
}

export function cadastrarPessoa(p: PessoaDemo, contas: Conta[]) {
  const b = banco();
  b.pessoas.push(p);
  for (const c of contas) b.contas[c.carteira_id] = { ...c };
  salvar(b);
}

/** Credita o líquido na conta de destino, se ela existir no banco demo. */
export function creditar(carteira_id: number, valor: number) {
  const b = banco();
  const c = b.contas[carteira_id];
  if (!c) return;
  c.saldo = Math.round((c.saldo + valor) * 100) / 100;
  salvar(b);
}

// --- Transações --------------------------------------------------------------------

export function guardarTransacao(t: Transacao) {
  const b = banco();
  b.transacoes.push(t);
  salvar(b);
}

export function todasTransacoes(): Transacao[] {
  return [...transacoesSemeadas, ...banco().transacoes];
}

// --- Chaves Pix --------------------------------------------------------------------

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function normalizarCelular(valor: string): string | null {
  let d = digitos(valor);
  if (d.startsWith("55") && (d.length === 12 || d.length === 13)) d = d.slice(2);
  if (d.length !== 10 && d.length !== 11) return null;
  return `+55${d}`;
}

/** Interpretações possíveis do que foi digitado (mesma ordem do backend). */
function candidatos(chave: string): [ChaveDemo["tipo"], string][] {
  const bruto = chave.trim();
  const res: [ChaveDemo["tipo"], string][] = [];
  if (UUID.test(bruto)) res.push(["aleatoria", bruto.toLowerCase()]);
  if (EMAIL.test(bruto)) res.push(["email", bruto.toLowerCase()]);
  const d = digitos(bruto);
  if (d.length === 11) res.push(["cpf", d]);
  if (d.length === 14) res.push(["cnpj", d]);
  const cel = normalizarCelular(bruto);
  if (cel && (bruto.startsWith("+") || [10, 11, 12, 13].includes(d.length)))
    res.push(["celular", cel]);
  return res;
}

/** Dono (carteira) de uma chave Pix, ou undefined. */
export function resolverChave(chave: string): number | undefined {
  const { chaves } = banco();
  for (const [tipo, valor] of candidatos(chave)) {
    const k = chaves.find((x) => x.tipo === tipo && x.valor === valor);
    if (k) return k.carteira_id;
  }
  return undefined;
}

export function chavesDa(carteira_id: number): ChaveDemo[] {
  return banco().chaves.filter((k) => k.carteira_id === carteira_id);
}

/** Cria a chave com as mesmas regras do backend. Lança Error com a mensagem para a tela. */
export function criarChaveDemo(
  conta: Conta,
  tipo: string,
  valor: string | undefined,
  novoId: number,
): ChaveDemo {
  const b = banco();
  if (b.chaves.filter((k) => k.carteira_id === conta.carteira_id).length >= MAX_CHAVES[conta.tipo])
    throw new Error(`Limite de ${MAX_CHAVES[conta.tipo]} chaves por conta atingido.`);
  let final: string;
  if (tipo === "aleatoria") {
    final = crypto.randomUUID();
  } else if (tipo === "cpf") {
    if (conta.tipo !== "PF") throw new Error("Chave CPF só para conta pessoal.");
    const dono = donoDaConta(conta.carteira_id);
    if (!dono?.cpf) throw new Error("Esta conta não tem CPF cadastrado.");
    final = dono.cpf;
  } else if (tipo === "cnpj") {
    if (conta.tipo !== "PJ") throw new Error("Chave CNPJ só para conta de empresa.");
    final = digitos(conta.cnpj ?? "");
    if (final.length !== 14) throw new Error("Esta empresa não tem CNPJ cadastrado.");
  } else if (tipo === "email") {
    if (!valor || !EMAIL.test(valor.trim())) throw new Error("E-mail inválido.");
    final = valor.trim().toLowerCase();
  } else if (tipo === "celular") {
    const cel = normalizarCelular(valor ?? "");
    if (!cel) throw new Error("Celular inválido. Use DDD + número.");
    final = cel;
  } else {
    throw new Error("Tipo de chave inválido.");
  }
  if (b.chaves.some((k) => k.tipo === tipo && k.valor === final))
    throw new Error("Esta chave já está cadastrada.");
  const k: ChaveDemo = {
    id: novoId,
    carteira_id: conta.carteira_id,
    tipo: tipo as ChaveDemo["tipo"],
    valor: final,
  };
  b.chaves.push(k);
  salvar(b);
  return k;
}

export function removerChaveDemo(carteira_id: number, id: number): boolean {
  const b = banco();
  const antes = b.chaves.length;
  b.chaves = b.chaves.filter((k) => !(k.id === id && k.carteira_id === carteira_id));
  if (b.chaves.length === antes) return false;
  salvar(b);
  return true;
}
