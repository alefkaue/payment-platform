import { describe, expect, it } from "vitest";
import { dataIso, idadeEm, problemaNascimento } from "./nascimento";

const HOJE = new Date(2026, 9, 15); // 15/10/2026

describe("data de nascimento no cadastro", () => {
  it("formata a data local sem deslocar o dia", () => {
    expect(dataIso(HOJE)).toBe("2026-10-15");
  });

  it("calcula a idade considerando mês e dia", () => {
    expect(idadeEm("2008-10-15", HOJE)).toBe(18);
    expect(idadeEm("2008-10-16", HOJE)).toBe(17);
    expect(idadeEm("2008-02-30", HOJE)).toBeNull();
  });

  it("recusa data no futuro", () => {
    expect(problemaNascimento("2026-10-16", HOJE)).toMatch(/futuro/);
  });

  it("barra menor de idade na hora", () => {
    expect(problemaNascimento("2008-10-16", HOJE)).toMatch(/18 anos/);
    expect(problemaNascimento("2026-10-15", HOJE)).toMatch(/18 anos/);
  });

  it("aceita quem faz 18 anos hoje", () => {
    expect(problemaNascimento("2008-10-15", HOJE)).toBeNull();
  });

  it("exige a data e recusa idade improvável", () => {
    expect(problemaNascimento("", HOJE)).toMatch(/Informe/);
    expect(problemaNascimento("1900-01-01", HOJE)).toMatch(/Confira/);
  });
});
