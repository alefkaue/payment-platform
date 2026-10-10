import { afterEach, expect, it, vi } from "vitest";
import { apuracaoPJ, consultarCobranca, listarFaturas } from "./api";
import { get } from "./http";
import { faseSplitDemo } from "./split-fase";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  get: vi.fn(),
}));
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

it.each(["informativo", "retencao", "demonstracao"] as const)(
  "API conserva contrato e recebível na fase %s",
  async (fase) => {
    const retido = fase !== "informativo";
    const cobranca = {
      id: 1,
      txid: "teste",
      split_fase: fase,
      valor: "1000.00",
      cbs: "90.00",
      ibs: "10.00",
      vai_reter_imposto: retido,
      status: "aberta",
      nfe_chave: "1".repeat(44),
    };
    vi.mocked(get).mockResolvedValueOnce({
      split_fase: fase,
      periodo: "2026-10",
      faturamento: "1000.00",
      imposto_destacado: "100.00",
      observacao: "Texto do servidor",
      split_retencao_desde: "2027-01-01",
      cbs_retido: retido ? "90.00" : "0.00",
      ibs_retido: retido ? "10.00" : "0.00",
      cbs_repassado: "0.00",
      ibs_repassado: "0.00",
      a_repassar: retido ? "100.00" : "0.00",
      creditos_informados: "0.00",
      restituicao_prevista: "0.00",
      transacoes_com_split: retido ? 1 : 0,
    });
    expect(await apuracaoPJ()).toMatchObject({
      split_fase: fase,
      periodo: "Outubro de 2026",
      faturamento: 1000,
      imposto_destacado: 100,
      imposto_retido: retido ? 100 : 0,
      observacao: "Texto do servidor",
      split_retencao_desde: "2027-01-01",
    });
    vi.mocked(get).mockResolvedValueOnce(cobranca);
    expect(await consultarCobranca("teste")).toMatchObject({
      split_fase: fase,
      cbs: 90,
      ibs: 10,
      vai_reter_imposto: retido,
    });
    vi.mocked(get).mockResolvedValueOnce([cobranca]);
    expect(await listarFaturas()).toMatchObject([
      { split_fase: fase, imposto: 100, liquido: retido ? 900 : 1000 },
    ]);
  },
);

it.each(["informativo", "retencao", "demonstracao"] as const)("demo aceita fase %s", (fase) => {
  vi.stubEnv("VITE_SPLIT_FASE", fase);
  expect(faseSplitDemo()).toBe(fase);
});
it("demo usa demonstracao como padrão", () => {
  vi.stubEnv("VITE_SPLIT_FASE", "");
  expect(faseSplitDemo()).toBe("demonstracao");
});
