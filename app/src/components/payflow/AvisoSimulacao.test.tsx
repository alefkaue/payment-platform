import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AvisoSimulacao } from "./AvisoSimulacao";

afterEach(cleanup);

it("avisa que valores e documentos não representam serviços financeiros reais", () => {
  render(<AvisoSimulacao />);
  const aviso = screen.getByRole("complementary", { name: "Ambiente de simulação" });
  expect(aviso.textContent).toContain("sem dinheiro real");
  expect(aviso.textContent).toContain("sem autenticação pelo emissor");
  expect(aviso.textContent).toContain("Use dados de teste");
});
