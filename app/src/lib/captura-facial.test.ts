import { describe, expect, it } from "vitest";
import { cotaPorPasso, MAX_QUADROS, selecionarQuadros, type Quadro } from "./captura-facial";

const serie = (vals: Partial<Quadro>[]): Quadro[] =>
  vals.map((v, i) => ({ img: `q${i}`, t: i * 100, blink: 0, smile: 0, yaw: 0, ...v }));

describe("seleção dos quadros da rajada", () => {
  it("não corta quando cabe na cota", () => {
    const qs = serie([{}, {}, {}]);
    expect(selecionarQuadros(qs, "sorrir", 10)).toEqual(qs);
  });

  it("guarda aberto, fechado e reaberto de cada piscada, em ordem de tempo", () => {
    const blinks = [0, 0, 0, 0.1, 0.9, 0.95, 0.1, 0, 0, 0, 0.8, 0.1, 0, 0, 0, 0, 0.7, 0.05, 0, 0];
    const qs = serie(blinks.map((blink) => ({ blink })));
    const sel = selecionarQuadros(qs, "piscar3", 10);
    expect(sel).toHaveLength(10);
    const fechados = sel.filter((q) => q.blink > 0.45).map((q) => q.img);
    expect(fechados).toEqual(expect.arrayContaining(["q5", "q10", "q16"]));
    expect(sel.map((q) => q.t)).toEqual([...sel.map((q) => q.t)].sort((a, b) => a - b));
    // depois de cada fechado há um quadro aberto selecionado
    for (const f of ["q5", "q10", "q16"]) {
      const i = sel.findIndex((q) => q.img === f);
      expect(sel.slice(i + 1).some((q) => q.blink < 0.3)).toBe(true);
    }
  });

  it("no sorriso guarda o neutro antes e os picos depois", () => {
    const smiles = [0.3, 0.1, 0.05, 0.2, 0.4, 0.7, 0.8, 0.75, 0.3, 0.2, 0.2, 0.2, 0.2, 0.2];
    const sel = selecionarQuadros(serie(smiles.map((smile) => ({ smile }))), "sorrir", 6);
    const imgs = sel.map((q) => q.img);
    expect(imgs).toEqual(expect.arrayContaining(["q2", "q5", "q6", "q7"]));
    expect(imgs.indexOf("q2")).toBeLessThan(imgs.indexOf("q6"));
  });

  it("na virada guarda o quadro de frente antes e os mais virados para o lado pedido", () => {
    const yaws = [0.1, 0.02, 0.1, 0.2, 0.3, 0.35, 0.3, -0.3, 0.1, 0.0, 0.1, 0.1];
    const sel = selecionarQuadros(serie(yaws.map((yaw) => ({ yaw }))), "virar_esquerda", 6);
    const imgs = sel.map((q) => q.img);
    expect(imgs).toEqual(expect.arrayContaining(["q1", "q4", "q5", "q6"]));
    expect(imgs).not.toContain("q7"); // o lado errado não é escolhido de propósito
  });

  it("a cota por passo respeita o teto do servidor", () => {
    for (const n of [1, 2, 4, 5]) expect(cotaPorPasso(n) * n).toBeLessThanOrEqual(MAX_QUADROS);
  });
});
