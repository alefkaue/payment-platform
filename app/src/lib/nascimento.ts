/** Regras da data de nascimento no cadastro (o servidor confere de novo: 18 a 120 anos). */

export const IDADE_MINIMA = 18;
export const IDADE_MAXIMA = 120;

/** Data local no formato do <input type="date"> (AAAA-MM-DD), sem passar por UTC. */
export function dataIso(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${dia}`;
}

/** Idade completa em anos na data `hoje`; null se a data for inválida. */
export function idadeEm(nascimentoIso: string, hoje: Date): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(nascimentoIso);
  if (!m) return null;
  const [a, mes, dia] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const d = new Date(a, mes - 1, dia);
  if (d.getFullYear() !== a || d.getMonth() !== mes - 1 || d.getDate() !== dia) return null;
  let idade = hoje.getFullYear() - a;
  if (hoje.getMonth() + 1 < mes || (hoje.getMonth() + 1 === mes && hoje.getDate() < dia)) idade--;
  return idade;
}

/** Mensagem de recusa, ou null se a data puder seguir no cadastro. */
export function problemaNascimento(nascimentoIso: string, hoje: Date = new Date()): string | null {
  if (!nascimentoIso) return "Informe a data de nascimento.";
  if (nascimentoIso > dataIso(hoje)) return "A data de nascimento não pode estar no futuro.";
  const idade = idadeEm(nascimentoIso, hoje);
  if (idade === null) return "Data de nascimento inválida.";
  if (idade < IDADE_MINIMA) return "Para abrir a conta é preciso ter 18 anos ou mais.";
  if (idade > IDADE_MAXIMA) return "Confira a data de nascimento.";
  return null;
}
