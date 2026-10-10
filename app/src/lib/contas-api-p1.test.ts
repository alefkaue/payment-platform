import { expect, it, vi } from "vitest";
import { listarFaturas, transacoes } from "./api";
import { get } from "./http";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  get: vi.fn(),
}));

it("API conserva abertas e pagas separáveis e exclui canceladas e estornadas", async () => {
  vi.mocked(get).mockResolvedValue(
    ["aberta", "paga", "cancelada", "estornada"].map((status, id) => ({
      id,
      txid: String(id),
      status,
      valor: "100.00",
      cbs: "1.00",
      ibs: "0.00",
      vai_reter_imposto: true,
      vencimento: id === 0 ? "2026-10-20" : null,
    })),
  );
  expect(await listarFaturas()).toMatchObject([
    { status: "pendente", liquido: 99, vencimento: "2026-10-20" },
    { status: "liquidado", liquido: 99, vencimento: "" },
  ]);
  expect(await listarFaturas("pagar")).toEqual([]);
});

it("API conserva o prazo informado do bloqueio no extrato", async () => {
  vi.mocked(get)
    .mockResolvedValueOnce({ carteira_id: 2 })
    .mockResolvedValueOnce([
      {
        id: 1,
        tipo: "transferencia",
        origem: { carteira_id: 1, nome: "Ana" },
        destino: { carteira_id: 2 },
        valor_bruto: "100.00",
        liquido: "100.00",
        cbs: "0.00",
        ibs: "0.00",
        status: "retida",
        bloqueio_ate: "2026-10-13T10:00:00Z",
        data_hora: "2026-10-10T10:00:00Z",
      },
    ]);
  expect(await transacoes()).toMatchObject([
    { status: "retida", bloqueio_ate: "2026-10-13T10:00:00Z" },
  ]);
});
