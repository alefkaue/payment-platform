/** Formato nacional; existência e posse exigem confirmação externa. */
const DDDS = new Set(
  "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split(
    " ",
  ),
);
export function normalizarCelular(valor: string): string | null {
  if (!/^[0-9+() .-]+$/.test(valor)) return null;
  if (
    valor.includes("+") &&
    (!valor.trim().startsWith("+55") || (valor.match(/\+/g) ?? []).length !== 1)
  )
    return null;
  let d = valor.replace(/\D/g, "");
  if (d.length === 13 && d.startsWith("55")) d = d.slice(2);
  if (d.length !== 11 || !DDDS.has(d.slice(0, 2)) || d[2] !== "9") return null;
  return `+55${d}`;
}
export function mascararCelular(valor: string): string {
  let d = valor.replace(/\D/g, "");
  if (d.length === 13 && d.startsWith("55")) d = d.slice(2);
  d = d.slice(0, 11);
  if (!d) return "";
  if (d.length <= 2) return `(${d}`;
  const local = d.slice(2);
  return `(${d.slice(0, 2)}) ${local.slice(0, 5)}${local.length > 5 ? `-${local.slice(5)}` : ""}`;
}
