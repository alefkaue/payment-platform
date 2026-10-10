import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { alterarVinculo, aumentaPoder, equipe, selecionarConta } from "./api";
import { contasDemo, equipeDemo, sessao } from "@/mocks/data";
import type { MembroEquipe } from "./types";

const original = equipeDemo.map((m) => ({ ...m }));
const contaOriginal = { ...sessao.conta };
const membro: MembroEquipe = {
  id: 999,
  nome: "Pessoa da equipe",
  email: null,
  papel: "operador",
  alcada: 100,
  status: "ativo",
  ativo: true,
};

describe("alterar vínculo na demonstração", () => {
  beforeEach(() => {
    selecionarConta({ ...contasDemo.PJ, papel: "admin", porte: "PME" });
    equipeDemo.splice(
      0,
      equipeDemo.length,
      { ...membro, id: 998, papel: "admin", alcada: null, eu: true },
      { ...membro },
    );
  });
  afterEach(() => {
    equipeDemo.splice(0, equipeDemo.length, ...original.map((m) => ({ ...m })));
    selecionarConta(contaOriginal);
  });
  it("altera papel e alçadas e mantém a diária quando omitida", async () => {
    expect(
      await alterarVinculo(999, { papel: "aprovador", alcada: "200.00", alcada_diaria: "500.00" }),
    ).toMatchObject({ papel: "aprovador", alcada: 200, alcada_diaria: 500 });
    await alterarVinculo(999, { alcada: "300" });
    expect((await equipe()).find((m) => m.id === 999)).toMatchObject({
      alcada: 300,
      alcada_diaria: 500,
    });
  });
  it("não pode tirar o último admin", async () => {
    await expect(alterarVinculo(998, { papel: "consulta" })).rejects.toThrow(
      /pelo menos um administrador/,
    );
    expect(equipeDemo[0]?.papel).toBe("admin");
  });
  it("permite reduzir admin quando outro admin continua ativo", async () => {
    await alterarVinculo(999, { papel: "admin" });
    expect(await alterarVinculo(998, { papel: "consulta" })).toMatchObject({
      papel: "consulta",
      alcada: 0,
      alcada_diaria: null,
    });
    await expect(alterarVinculo(999, { papel: "consulta" })).rejects.toThrow(/Só administrador/);
  });
  it("MEI recusa papéis poderosos e operador sem limite, mas preserva o titular", async () => {
    sessao.conta.porte = "MEI";
    await expect(alterarVinculo(999, { papel: "admin" })).rejects.toThrow(/não pode ser concedido/);
    await expect(alterarVinculo(999, { papel: "aprovador" })).rejects.toThrow(
      /não pode ser concedido/,
    );
    await expect(alterarVinculo(999, { sem_limite: true })).rejects.toThrow(/alçada definida/);
    expect(await alterarVinculo(998, { papel: "admin" })).toMatchObject({ papel: "admin" });
  });
  it("Grande exige alçada do operador; PME permite sem limite", async () => {
    sessao.conta.porte = "GRANDE";
    await expect(alterarVinculo(999, { sem_limite: true })).rejects.toThrow(/alçada definida/);
    sessao.conta.porte = "PME";
    expect(await alterarVinculo(999, { sem_limite: true })).toMatchObject({
      alcada: null,
      alcada_diaria: null,
    });
  });
  it("recusa diária menor, valores inválidos, vínculo ausente e acesso encerrado", async () => {
    await expect(alterarVinculo(999, { alcada_diaria: "50" })).rejects.toThrow(/menor/);
    for (const alcada of ["-1", "NaN", "1.234"])
      await expect(alterarVinculo(999, { alcada })).rejects.toThrow(/válida/);
    await expect(alterarVinculo(-1, {})).rejects.toThrow(/não encontrada/);
    equipeDemo[1]!.status = "revogado";
    await expect(alterarVinculo(999, {})).rejects.toThrow(/encerrado/);
  });
  it("recusa quem não administra", async () => {
    sessao.conta.papel = "operador";
    await expect(alterarVinculo(999, {})).rejects.toThrow(/Só administrador/);
    sessao.conta.tipo = "PF";
    sessao.conta.papel = "admin";
    await expect(alterarVinculo(999, {})).rejects.toThrow(/Só administrador/);
  });
});

it("detecta aumento de papel, alçada, diária e remoção de limite", () => {
  for (const mudanca of [
    { papel: "aprovador" as const },
    { papel: "admin" as const },
    { alcada: 200 },
    { alcada_diaria: 200 },
    { alcada: null },
  ])
    expect(aumentaPoder(membro, { ...membro, ...mudanca })).toBe(true);
  expect(aumentaPoder(membro, { ...membro, alcada: 50 })).toBe(false);
  expect(aumentaPoder(membro, { ...membro, papel: "consulta", alcada: 0 })).toBe(false);
  expect(aumentaPoder(membro, { ...membro })).toBe(false);
});
