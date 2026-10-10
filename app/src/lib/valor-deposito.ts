/** Limite do depósito de demonstração, também conferido pelo servidor. */
export const LIMITE_DEPOSITO = 10_000;

/** Digitação em centavos: 1 -> 0,01; 100 -> 1,00. Null rejeita excesso. */
export function mascararDeposito(entrada: string): string | null {
  const digitos = entrada.replace(/[^0-9]/g, "").replace(/^0+/, "");
  if (!entrada) return "";
  if (digitos.length > 7 || (digitos.length === 7 && digitos > "1000000")) return null;
  const d = digitos.padStart(3, "0");
  const reais = d.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${reais},${d.slice(-2)}`;
}
