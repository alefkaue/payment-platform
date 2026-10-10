import { expect, it } from "vitest";
import { mascararDeposito } from "./valor-deposito";
it.each([
  ["1", "0,01"],
  ["10", "0,10"],
  ["100", "1,00"],
  ["1000", "10,00"],
  ["100000", "1.000,00"],
  ["1000000", "10.000,00"],
  ["R$ 1.234,56", "1.234,56"],
  ["", ""],
  ["000", "0,00"],
])("formata %s", (entrada, esperado) => {
  expect(mascararDeposito(entrada)).toBe(esperado);
});
it.each(["1000001", "9999999", "999999999999999999"])("recusa excesso %s", (valor) => {
  expect(mascararDeposito(valor)).toBeNull();
});

it("avisa o limite do banco antes de enviar um depósito acima do teto", async () => {
  const { depositar } = await import("./api");
  await expect(depositar({ valor: 10000.01 })).rejects.toThrow(
    "O limite do banco é de R$ 10.000,00 por depósito.",
  );
});
