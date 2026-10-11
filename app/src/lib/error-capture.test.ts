import { afterEach, expect, it, vi } from "vitest";
import { describeError, formatConsoleErrorArgs } from "./error-capture";

afterEach(() => vi.unstubAllEnvs());

it("produção omite mensagem, pilha e causa de erros", () => {
  vi.stubEnv("PROD", true);
  const erro = new Error("senha=teste-secreto", { cause: new Error("cpf=cliente-teste") });
  erro.stack = "pilha com token=teste";
  expect(describeError(erro)).toBe("Erro interno no servidor.");
  expect(describeError({ token: "teste" })).toBe("Erro interno no servidor.");
});

it("desenvolvimento conserva diagnóstico de erros", () => {
  vi.stubEnv("PROD", false);
  expect(describeError(new Error("diagnóstico de teste"))).toContain("diagnóstico de teste");
});

it("produção oculta todos os argumentos, inclusive textos e objetos comuns", () => {
  vi.stubEnv("PROD", true);
  const segredo = { token: "credencial-fictícia", cpf: "documento-fictício" };
  expect(formatConsoleErrorArgs(["senha=fictícia", segredo, new Error("causa-fictícia")])).toEqual([
    "Erro interno no servidor.",
  ]);
});

it("produção não serializa objetos de log", () => {
  vi.stubEnv("PROD", true);
  const serializar = vi.fn(() => {
    throw new Error("Não deve ser chamado");
  });
  expect(formatConsoleErrorArgs([{ toJSON: serializar }])).toEqual(["Erro interno no servidor."]);
  expect(serializar).not.toHaveBeenCalled();
});

it("console.error instalado não envia dados brutos em produção", async () => {
  vi.stubEnv("PROD", true);
  const anterior = console.error;
  const saida = vi.fn();
  console.error = saida;
  try {
    vi.resetModules();
    await import("./error-capture");
    console.error("senha=fictícia", { token: "fictício" }, new Error("dado fictício"));
    expect(saida).toHaveBeenCalledExactlyOnceWith("Erro interno no servidor.");
  } finally {
    console.error = anterior;
  }
});

it("desenvolvimento conserva argumentos comuns e descreve Error", () => {
  vi.stubEnv("PROD", false);
  const metadados = { teste: true };
  const args = formatConsoleErrorArgs(["diagnóstico", metadados, new Error("falha fictícia")]);
  expect(args[0]).toBe("diagnóstico");
  expect(args[1]).toBe(metadados);
  expect(args[2]).toContain("falha fictícia");
});
