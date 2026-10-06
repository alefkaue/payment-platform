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
