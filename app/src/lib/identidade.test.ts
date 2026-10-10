import { beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => vi.resetModules());

describe("verificação de identidade na demonstração", () => {
  it("começa aprovada e devolve uma cópia do estado", async () => {
    const { minhaVerificacao } = await import("./api");
    const resultado = await minhaVerificacao();
    expect(resultado).toEqual({ status: "aprovado", caso: null });
    resultado.status = "reprovado";
    expect((await minhaVerificacao()).status).toBe("aprovado");
  });

  it.each(["rg", "cnh", "cin"] as const)(
    "exige verso para %s sem alterar o status",
    async (tipo) => {
      const { minhaVerificacao, reenviarDocumento } = await import("./api");
      await expect(reenviarDocumento({ tipo, frente: "foto" })).rejects.toThrow("verso");
      expect((await minhaVerificacao()).status).toBe("aprovado");
      const resultado = await reenviarDocumento({ tipo, frente: "foto", verso: "foto" });
      expect(resultado.status).toBe("em_analise");
      expect(await minhaVerificacao()).toMatchObject({
        status: "em_analise",
        caso: { id: resultado.caso_id, motivos: [] },
      });
    },
  );

  it("aceita passaporte só com a página da foto e não guarda imagens", async () => {
    const { minhaVerificacao, reenviarDocumento } = await import("./api");
    await expect(reenviarDocumento({ tipo: "passaporte", frente: "" })).rejects.toThrow("frente");
    await reenviarDocumento({ tipo: "passaporte", frente: "imagem privada" });
    expect(JSON.stringify(await minhaVerificacao())).not.toContain("imagem privada");
    expect((await minhaVerificacao()).status).toBe("em_analise");
  });
});
