import { beforeEach, describe, expect, it } from "vitest";
import { auditoriaEmpresa, descreverAcao } from "./api";
import { detalheAuditoria, filtrarAuditoria } from "./auditoria";
import { contasDemo, sessao } from "@/mocks/data";

beforeEach(() => {
  sessao.conta = { ...contasDemo.PJ };
});

describe("auditoria da empresa em demonstração", () => {
  it("devolve oito eventos da empresa, ordenados, com ator e descrição", async () => {
    const itens = await auditoriaEmpresa();
    expect(itens).toHaveLength(8);
    expect(
      itens.every(
        (a) => a.empresa_id === contasDemo.PJ.id && a.ator && a.descricao === descreverAcao(a.acao),
      ),
    ).toBe(true);
    expect(itens.map((a) => a.id)).toEqual([8, 7, 6, 5, 4, 3, 2, 1]);
    expect((await auditoriaEmpresa(2)).map((a) => a.id)).toEqual([8, 7]);
    expect(await auditoriaEmpresa(200)).toHaveLength(8);
  });
  it("permite aprovador e recusa PF, operador e consulta", async () => {
    sessao.conta = { ...contasDemo.PJ, papel: "aprovador" };
    expect(await auditoriaEmpresa()).toHaveLength(8);
    for (const papel of ["operador", "consulta"] as const) {
      sessao.conta = { ...contasDemo.PJ, papel };
      await expect(auditoriaEmpresa()).rejects.toThrow(/Só administradores/);
    }
    sessao.conta = { ...contasDemo.PF };
    await expect(auditoriaEmpresa()).rejects.toThrow(/exclusiva para empresas/);
  });
  it("recusa limites inválidos", async () => {
    for (const limite of [0, 201, 1.5, NaN])
      await expect(auditoriaEmpresa(limite)).rejects.toThrow(/entre 1 e 200/);
  });
  it("combina texto e tipo, busca ator e preserva os eventos", async () => {
    const itens = await auditoriaEmpresa();
    expect(filtrarAuditoria(itens, "", "Todos")).toEqual(itens);
    expect(filtrarAuditoria(itens, "  MARINA  ", "Aprovações").map((a) => a.acao)).toEqual([
      "operacao_aprovada",
    ]);
    expect(filtrarAuditoria(itens, "cobrança", "Pagamentos").map((a) => a.acao)).toEqual([
      "cobranca_criada",
    ]);
    expect(filtrarAuditoria(itens, "ana@", "Acessos").map((a) => a.acao)).toEqual([
      "convite_aceito",
    ]);
    expect(filtrarAuditoria(itens, "inexistente", "Todos")).toEqual([]);
    expect(filtrarAuditoria(itens, "", "Acessos")).toHaveLength(4);
    expect(itens).toHaveLength(8);
  });
  it("resume dinheiro e referências sem expor campos desconhecidos", () => {
    const resumo = detalheAuditoria({
      valor: "1500.00",
      operacao_id: 7,
      transacao_id: 8,
      segredo: "oculto",
    });
    expect(resumo).toContain("1.500,00");
    expect(resumo).toContain("Operação #7 · Transação #8");
    expect(resumo).not.toContain("oculto");
    expect(detalheAuditoria(null)).toBe("");
    expect(
      detalheAuditoria({
        valor: "inválido",
        operacao_id: {},
        transacao_id: -1,
      }),
    ).toBe("");
  });
});
