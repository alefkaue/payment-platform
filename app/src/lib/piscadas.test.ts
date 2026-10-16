import { describe, expect, it } from "vitest";
import { ContadorPiscadas, limiaresPiscada } from "./piscadas";

function serie(base: number, pico: number, n: number): number[] {
  const s: number[] = Array(8).fill(base);
  for (let i = 0; i < n; i++) s.push(pico, pico, ...Array(4).fill(base));
  return s;
}

function contar(valores: number[], yaw = 0): number {
  const c = new ContadorPiscadas();
  for (const b of valores) c.observar(b, yaw);
  return c.piscadas;
}

describe("piscadas calibradas pela pessoa", () => {
  it("conta com o olho aberto alto (olhando para baixo / óculos)", () => {
    expect(contar(serie(0.34, 0.85, 3))).toBe(3);
  });

  it("continua contando o caso comum", () => {
    expect(contar(serie(0.05, 0.7, 2))).toBe(2);
  });

  it("tremor pequeno não vira piscada", () => {
    expect(contar(Array(5).fill([0.3, 0.42, 0.31, 0.45, 0.33]).flat())).toBe(0);
  });

  it("rosto virado não conta", () => {
    expect(contar(serie(0.05, 0.7, 2), 0.3)).toBe(0);
  });

  it("é mais exigente que o servidor (fechado 0.35/aberto 0.30 com base baixa)", () => {
    const { fechado, aberto } = limiaresPiscada(0.05);
    expect(fechado).toBeGreaterThanOrEqual(0.35);
    expect(aberto).toBeLessThanOrEqual(0.3);
    const alto = limiaresPiscada(0.34);
    expect(alto.fechado).toBeGreaterThanOrEqual(0.34 + 0.25);
    expect(alto.aberto).toBeLessThanOrEqual(0.34 + 0.12);
  });

  it("recomeçar zera a contagem e mantém a calibração", () => {
    const c = new ContadorPiscadas();
    for (const b of serie(0.34, 0.85, 1)) c.observar(b, 0);
    c.recomecar();
    expect(c.piscadas).toBe(0);
    expect(c.base).toBeCloseTo(0.34);
  });
});
