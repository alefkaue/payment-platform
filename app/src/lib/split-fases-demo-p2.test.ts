import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});
it.each(["informativo", "retencao", "demonstracao"] as const)(
  "dados demo são coerentes na fase %s",
  async (fase) => {
    vi.stubEnv("VITE_SPLIT_FASE", fase);
    vi.resetModules();
    const dados = await import("@/mocks/data");
    const api = await import("./api");
    dados.sessao.conta = { ...dados.contasDemo.PJ };
    const retencao = fase !== "informativo";
    const apuracao = await api.apuracaoPJ();
    expect(apuracao.split_fase).toBe(fase);
    expect(apuracao.imposto_destacado).toBeGreaterThan(0);
    expect(apuracao.imposto_retido > 0).toBe(retencao);
    const vendas = dados.transacoes.filter(
      (t) => t.destino_carteira_id === 3050 && t.cbs + t.ibs > 0,
    );
    expect(vendas.length).toBeGreaterThan(0);
    for (const venda of vendas) {
      expect(venda.aplicou_split).toBe(retencao);
      expect(venda.liquido).toBe(
        retencao ? venda.valor_bruto - venda.cbs - venda.ibs : venda.valor_bruto,
      );
    }
    const [cobranca] = await api.criarCobranca({
      valor: 1000,
      nota_fiscal: { chave: "1".repeat(44), cbs: 90, ibs: 10 },
    });
    expect(cobranca).toMatchObject({ split_fase: fase, vai_reter_imposto: retencao });
    const faturas = await api.listarFaturas();
    expect(faturas.find((f) => f.txid === cobranca?.txid)).toMatchObject({
      imposto: 100,
      liquido: retencao ? 900 : 1000,
    });
  },
);
