import { expect, it, vi } from "vitest";
import { alterarVinculo } from "./api";
import { patch } from "./http";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  patch: vi.fn(),
}));

it("PATCH envia decimais e rosto e conserva os dados da pendência da Grande", async () => {
  vi.mocked(patch).mockResolvedValue({
    id: 7,
    nome: "Ana",
    email: null,
    cpf: null,
    cargo: null,
    papel: "operador",
    alcada: "100.00",
    alcada_diaria: "200.00",
    status: "ativo",
    ativo: true,
    eu: false,
    ultimo_acesso_em: null,
    aguardando_aprovacao: true,
    operacao_id: 42,
  });
  const biometria = { desafio_id: "teste", quadros: [] };
  const mudancas = { alcada: "300.00", alcada_diaria: "500.00" };
  expect(await alterarVinculo(7, mudancas, biometria)).toMatchObject({
    alcada: 100,
    alcada_diaria: 200,
    aguardando_aprovacao: true,
    operacao_id: 42,
  });
  expect(patch).toHaveBeenCalledWith("/empresas/atual/vinculos/7", { ...mudancas, biometria });
});

it("PATCH sem rosto conserva a mensagem de erro do servidor", async () => {
  vi.mocked(patch).mockRejectedValue(
    new Error("A empresa precisa de pelo menos um administrador ativo."),
  );
  await expect(alterarVinculo(7, { papel: "consulta" })).rejects.toThrow(
    /pelo menos um administrador/,
  );
  expect(patch).toHaveBeenLastCalledWith("/empresas/atual/vinculos/7", { papel: "consulta" });
});
