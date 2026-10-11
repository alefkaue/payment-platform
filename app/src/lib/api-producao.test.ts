import { expect, it } from "vitest";
import { validarApiProducao } from "../../scripts/cabecalhos.mjs";

it.each([
  "http://api.teste",
  "javascript:alert(1)",
  "//api.teste",
  "invalida",
  "https://usuario:senha@api.teste",
  "https://api.teste?token=teste",
  "https://api.teste#teste",
])("produção rejeita configuração insegura: %s", (url) => {
  expect(() => validarApiProducao({ VITE_API_URL: url })).toThrow();
});
it("produção aceita HTTPS com caminho da API", () => {
  expect(() => validarApiProducao({ VITE_API_URL: "https://api.teste/v1" })).not.toThrow();
});
it("produção sem API exige demonstração explícita", () => {
  expect(() => validarApiProducao({})).toThrow();
  expect(() => validarApiProducao({ VITE_MODO_DEMO: "1" })).not.toThrow();
});
it("modo demonstração não libera API em HTTP no build de produção", () => {
  expect(() =>
    validarApiProducao({ VITE_MODO_DEMO: "1", VITE_API_URL: "http://api.teste" }),
  ).toThrow();
});
