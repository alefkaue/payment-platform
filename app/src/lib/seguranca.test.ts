/** Segurança no modo demonstração: aparelhos, sessões e atividade. */
import { describe, expect, it } from "vitest";
import {
  bloquearAparelho,
  descreverAcao,
  desbloquearAparelho,
  encerrarOutrasSessoes,
  meusAparelhos,
  minhaAtividade,
  minhasSessoes,
  removerAparelho,
} from "./api";

const bio = { desafio_id: "demo", quadros: [] };

describe("segurança (demonstração)", () => {
  it("marca o aparelho atual, bloqueia, desbloqueia e remove", async () => {
    const lista = await meusAparelhos();
    expect(lista.filter((a) => a.atual)).toHaveLength(1);
    const outro = lista.find((a) => !a.atual)!;
    await bloquearAparelho(outro.id);
    expect((await meusAparelhos()).find((a) => a.id === outro.id)).toMatchObject({
      bloqueado: true,
      confiavel: false,
    });
    await desbloquearAparelho(outro.id, bio);
    expect((await meusAparelhos()).find((a) => a.id === outro.id)?.bloqueado).toBe(false);
    await removerAparelho(outro.id);
    expect((await meusAparelhos()).some((a) => a.id === outro.id)).toBe(false);
  });

  it("encerrar as outras sessões mantém só a atual", async () => {
    expect((await minhasSessoes()).length).toBeGreaterThan(1);
    expect(await encerrarOutrasSessoes()).toBeGreaterThan(0);
    const restantes = await minhasSessoes();
    expect(restantes).toHaveLength(1);
    expect(restantes[0]?.atual).toBe(true);
  });

  it("descreve as ações da trilha em português", async () => {
    expect(descreverAcao("login_aparelho_novo")).toBe("Entrou de um aparelho novo");
    expect(descreverAcao("acao_desconhecida")).toBe("Acao desconhecida");
    expect((await minhaAtividade()).every((a) => a.descricao.length > 0)).toBe(true);
  });
});
