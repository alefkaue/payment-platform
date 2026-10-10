/** Soma exata apenas para a prévia da folha; o servidor calcula o débito. */
export function centavosFolha(valor: string): bigint {
  const decimal = valor.trim().replace(",", ".");
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(decimal))
    throw new Error("Informe um valor válido com até duas casas decimais.");
  const [inteiro = "0", fracao = ""] = decimal.split(".");
  return BigInt(inteiro) * 100n + BigInt(fracao.padEnd(2, "0"));
}
export function decimalFolha(valor: bigint): string {
  return `${valor / 100n}.${String(valor % 100n).padStart(2, "0")}`;
}
export function totalFolha(valores: string[]): string {
  return decimalFolha(valores.reduce((total, valor) => total + centavosFolha(valor), 0n));
}
