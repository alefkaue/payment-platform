import type { AuditoriaEmpresa } from "./api";
import { fmtBRL } from "./format";
import { num } from "./http";

export type TipoAuditoria = "Todos" | "Acessos" | "Pagamentos" | "Aprovações";

const tipos: Record<Exclude<TipoAuditoria, "Todos">, readonly string[]> = {
  Acessos: [
    "convite",
    "convite_aceito",
    "convite_recusado",
    "usuario_convidado",
    "suspender",
    "reativar",
    "revogar",
    "alteracao",
    "usuario_suspenso",
    "usuario_reativado",
    "usuario_revogado",
    "permissao_alterada",
    "criar_conta_pj",
    "documento_empresa_enviado",
    "login",
    "login_aparelho_novo",
  ],
  Pagamentos: [
    "transferencia",
    "cobranca_criada",
    "cobranca_paga",
    "cobranca_cancelada",
    "cobranca_estornada",
    "credito_declarado",
    "limites_alterados",
  ],
  Aprovações: [
    "operacao_pendente",
    "operacao_aprovada",
    "operacao_rejeitada",
    "operacao_cancelada",
    "operacao_conciliada",
    "aprovacao_parcial",
    "acesso_aprovado",
  ],
};

/** Combina os filtros sobre a lista carregada, sem alterar a ordem da trilha. */
export function filtrarAuditoria(
  itens: readonly AuditoriaEmpresa[],
  texto: string,
  tipo: TipoAuditoria,
): AuditoriaEmpresa[] {
  const busca = texto.trim().toLocaleLowerCase("pt-BR");
  return itens.filter(
    (a) =>
      (tipo === "Todos" || tipos[tipo].includes(a.acao)) &&
      `${a.descricao} ${a.ator}`.toLocaleLowerCase("pt-BR").includes(busca),
  );
}

/** Exibe apenas valor e referências conhecidas; nunca o JSON inteiro. */
export function detalheAuditoria(detalhe: AuditoriaEmpresa["detalhe"]): string {
  if (!detalhe) return "";
  const partes: string[] = [];
  const valor = detalhe["valor"];
  if (typeof valor === "string" && /^\d+(\.\d{1,2})?$/.test(valor) && Number.isFinite(num(valor)))
    partes.push(fmtBRL(num(valor)));
  for (const [campo, rotulo] of [
    ["operacao_id", "Operação"],
    ["transacao_id", "Transação"],
  ] as const) {
    const id = detalhe[campo];
    if (typeof id === "number" && Number.isInteger(id) && id > 0) partes.push(`${rotulo} #${id}`);
  }
  return partes.join(" · ");
}
