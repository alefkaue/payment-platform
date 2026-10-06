const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export const fmtBRL = (n: number) => brl.format(n);
export const fmtData = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
export const fmtId = (n: number) => `#${String(n).padStart(6, "0")}`;
export const fmtPontos = (n: number) => new Intl.NumberFormat("pt-BR").format(n);

/** Iniciais (até 2) para avatar. "Rodoforte Autopeças Ltda" -> "RA". */
export function iniciais(nome?: string): string {
  const partes = (nome ?? "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "·";
  return partes
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

/** Primeiro nome / nome curto para a saudação. */
export function primeiroNome(nome?: string): string | undefined {
  const p = (nome ?? "").trim().split(/\s+/).filter(Boolean)[0];
  return p || undefined;
}

export function maskDoc(v: string, tipo: "PF" | "PJ") {
  const d = v.replace(/\D/g, "").slice(0, tipo === "PF" ? 11 : 14);
  if (tipo === "PF")
    return d
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  return d
    .replace(/(\d{2})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

/** Parses "1.234,56" or "1234.56" into a number. */
export function parseValor(v: string): number {
  const s = v.trim();
  if (!s) return NaN;
  const norm = s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s;
  return Number(norm);
}
