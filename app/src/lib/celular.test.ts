import { describe, expect, it } from "vitest";
import { mascararCelular, normalizarCelular } from "./celular";
describe("celular brasileiro", () => {
  it.each(["11987654321", "(11) 98765-4321", "+55 (11) 98765-4321", "5599987654321"])(
    "aceita e normaliza %s",
    (v) => expect(normalizarCelular(v)).toMatch(/^\+55\d{11}$/),
  );
  it.each([
    "1134567890",
    "1198765432",
    "119876543210",
    "20987654321",
    "11887654321",
    "abc11987654321",
    "+1 11987654321",
  ])("recusa %s", (v) => expect(normalizarCelular(v)).toBeNull());
  it("limita o campo a DDD e nove dígitos", () => {
    expect(mascararCelular("119876543219999")).toBe("(11) 98765-4321");
    expect(mascararCelular("+55 (11) 98765-4321")).toBe("(11) 98765-4321");
  });
});
