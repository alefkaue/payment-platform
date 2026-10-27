import { describe, expect, it } from "vitest";
import {
  giroDoRosto,
  mediana,
  medirRosto,
  OCULOS_LIMIAR,
  orientarRosto,
  recusaQualidade,
  type MedidasRosto,
} from "./qualidade-rosto";

const boa: MedidasRosto = {
  rostos: 1,
  altura: 0.6,
  centroX: 0.5,
  centroY: 0.5,
  brilho: 120,
  estourado: 0,
  contraluz: 0,
  oculos: 0,
};
describe("orientação do rosto", () => {
  it.each([
    [{ rostos: 0 }, "Posicione"],
    [{ rostos: 2 }, "sozinho"],
    [{ altura: 0.24 }, "Aproxime"],
    [{ altura: 0.96 }, "Afaste"],
    [{ centroX: 0.8 }, "Centralize"],
    [{ centroY: 0.8 }, "Centralize"],
    [{ brilho: 29 }, "escuro"],
  ] as const)("orienta para %j", (mudanca, texto) => {
    expect(orientarRosto({ ...boa, ...mudanca }, true)).toContain(texto);
  });
  it("respeita a prioridade rosto, distância, centro e luz", () => {
    const ruim = {
      ...boa,
      rostos: 0,
      altura: 0.2,
      centroX: 0.9,
      brilho: 20,
      estourado: 0.8,
      contraluz: 100,
      oculos: 3,
    };
    expect(orientarRosto(ruim, true)).toContain("Posicione");
    ruim.rostos = 1;
    expect(orientarRosto(ruim, true)).toContain("Aproxime");
    ruim.altura = 0.6;
    expect(orientarRosto(ruim, true)).toContain("Centralize");
    ruim.centroX = 0.5;
    expect(orientarRosto(ruim, true)).toContain("escuro");
    // Facilitado em 26/10/2026: luz forte, contraluz e óculos não bloqueiam mais.
    ruim.brilho = 120;
    expect(orientarRosto(ruim, true)).toBeNull();
  });
  it("aceita os limites de luz e não bloqueia por óculos", () => {
    expect(orientarRosto({ ...boa, brilho: 30, estourado: 0.8, contraluz: 120 }, true)).toBeNull();
    expect(orientarRosto({ ...boa, oculos: OCULOS_LIMIAR }, true)).toBeNull();
  });
  it.each([
    "Está escuro",
    "Luz forte demais",
    "Há muita luz atrás de você",
    "Tire os óculos",
    "Há mais de um rosto na imagem",
    "O rosto mudou durante a verificação",
  ])("reconhece a recusa %s", (msg) => expect(recusaQualidade(msg)).toBe(true));
  it("não trata senha inválida como qualidade", () =>
    expect(recusaQualidade("Senha inválida")).toBe(false));
});

describe("medição dos pixels", () => {
  const pontos = () => {
    const p = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }));
    p[0] = { x: 0.1, y: 0.1 };
    p[1] = { x: 0.9, y: 0.9 };
    p[133] = { x: 0.4, y: 0.4 }; // cantos internos dos olhos: 16 px de distância em 80 px
    p[362] = { x: 0.6, y: 0.4 };
    p[168] = { x: 0.5, y: 0.4 };
    return p;
  };
  const pintar = (px: Uint8ClampedArray, x0: number, x1: number, y0: number, y1: number) => {
    for (let y = y0; y < y1; y++)
      for (let x = x0; x < x1; x++) px.fill(20, (y * 80 + x) * 4, (y * 80 + x) * 4 + 3);
  };
  it("acusa óculos com a barra horizontal da armação entre os olhos", () => {
    const px = new Uint8ClampedArray(80 * 80 * 4).fill(140);
    expect(medirRosto(px, 80, 80, pontos(), 1).oculos).toBe(0);
    pintar(px, 30, 50, 32, 34); // ponte da armação
    expect(medirRosto(px, 80, 80, pontos(), 1).oculos).toBeGreaterThanOrEqual(OCULOS_LIMIAR);
  });
  it("não confunde bordas verticais (nariz de lado, fundo) com óculos", () => {
    const px = new Uint8ClampedArray(80 * 80 * 4).fill(140);
    pintar(px, 38, 40, 20, 60); // lateral do nariz / borda do fundo ao virar o rosto
    pintar(px, 44, 80, 20, 60);
    expect(medirRosto(px, 80, 80, pontos(), 1).oculos).toBeLessThan(OCULOS_LIMIAR);
  });
  it("mede o giro e a mediana", () => {
    const p = pontos();
    p[234] = { x: 0.3, y: 0.5 };
    p[454] = { x: 0.7, y: 0.5 };
    p[1] = { x: 0.6, y: 0.5 };
    expect(giroDoRosto(p)).toBeCloseTo(0.25);
    expect(mediana([0.9, 0.1, 0.2])).toBe(0.2);
    expect(mediana([])).toBe(0);
  });
  it("mede a caixa do rosto e exclui o rosto da média do fundo", () => {
    const pixels = new Uint8ClampedArray(10 * 10 * 4);
    for (let y = 0; y < 10; y++)
      for (let x = 0; x < 10; x++) {
        const i = (y * 10 + x) * 4;
        pixels.fill(x >= 2 && x < 8 && y >= 2 && y < 8 ? 50 : 200, i, i + 3);
        pixels[i + 3] = 255;
      }
    const m = medirRosto(
      pixels,
      10,
      10,
      [
        { x: 0.2, y: 0.2 },
        { x: 0.8, y: 0.8 },
      ],
      1,
    );
    expect(m.brilho).toBeCloseTo(50);
    expect(m.contraluz).toBeCloseTo(150);
    expect(m.estourado).toBe(0);
    expect(m.altura).toBe(0.6);
  });
  it("mede pixels estourados e ausência de rosto", () => {
    const pixels = new Uint8ClampedArray(16 * 4).fill(255);
    expect(
      medirRosto(
        pixels,
        4,
        4,
        [
          { x: 0, y: 0 },
          { x: 1, y: 1 },
        ],
        1,
      ).estourado,
    ).toBe(1);
    expect(orientarRosto(medirRosto(pixels, 4, 4, [], 0), true)).toContain("Posicione");
  });
});
