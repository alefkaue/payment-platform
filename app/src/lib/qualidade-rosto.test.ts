import { describe, expect, it } from "vitest";
import {
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
    [{ altura: 0.39 }, "Aproxime"],
    [{ altura: 0.86 }, "Afaste"],
    [{ centroX: 0.7 }, "Centralize"],
    [{ centroY: 0.7 }, "Centralize"],
    [{ brilho: 54 }, "escuro"],
    [{ estourado: 0.26 }, "forte demais"],
    [{ contraluz: 86 }, "atrás"],
    [{ oculos: OCULOS_LIMIAR }, "óculos"],
  ] as const)("orienta para %j", (mudanca, texto) => {
    expect(orientarRosto({ ...boa, ...mudanca }, true)).toContain(texto);
  });
  it("respeita a prioridade rosto, distância, centro, luz e óculos", () => {
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
    ruim.brilho = 120;
    expect(orientarRosto(ruim, true)).toContain("forte demais");
    ruim.estourado = 0;
    expect(orientarRosto(ruim, true)).toContain("atrás");
    ruim.contraluz = 0;
    expect(orientarRosto(ruim, true)).toContain("óculos");
  });
  it("aceita os limites de luz e só verifica óculos no cadastro", () => {
    expect(orientarRosto({ ...boa, brilho: 55, estourado: 0.25, contraluz: 85 }, true)).toBeNull();
    expect(orientarRosto({ ...boa, oculos: 3 }, false)).toBeNull();
  });
  it("permite os movimentos dos passos sem perder o bloqueio de luz e múltiplos rostos", () => {
    expect(orientarRosto({ ...boa, centroX: 0.8, altura: 0.3 }, false, false)).toBeNull();
    expect(orientarRosto({ ...boa, brilho: 20 }, false, false)).toContain("escuro");
    expect(orientarRosto({ ...boa, rostos: 2 }, false, false)).toContain("sozinho");
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
  it("compara bordas na ponte do nariz com a testa", () => {
    const pontos = Array.from({ length: 363 }, () => ({ x: 0.5, y: 0.5 }));
    pontos[0] = { x: 0.1, y: 0.1 };
    pontos[1] = { x: 0.9, y: 0.9 };
    pontos[133] = { x: 0.4, y: 0.4 };
    pontos[362] = { x: 0.6, y: 0.4 };
    pontos[168] = { x: 0.5, y: 0.4 };
    pontos[10] = { x: 0.5, y: 0.2 };
    const pixels = new Uint8ClampedArray(80 * 80 * 4).fill(120);
    expect(medirRosto(pixels, 80, 80, pontos, 1).oculos).toBe(0);
    for (let y = 28; y < 36; y++)
      for (let x = 34; x < 40; x++) {
        const i = (y * 80 + x) * 4;
        pixels.fill(0, i, i + 3);
      }
    expect(medirRosto(pixels, 80, 80, pontos, 1).oculos).toBeGreaterThanOrEqual(OCULOS_LIMIAR);
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
