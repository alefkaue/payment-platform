/** Troca e recuperação de senha no modo demonstração (sem VITE_API_URL). */
import { beforeEach, describe, expect, it } from "vitest";
import {
  concluirCadastro,
  concluirLogin,
  concluirRecuperacao,
  iniciarRecuperacao,
  login,
  registrar,
  trocarSenha,
} from "./api";

const bio = { desafio_id: "demo", quadros: [] };
const SENHA = "Cofre-Astro#2026";
const NOVA = "Outra-Chave#Forte42";

async function cadastrar(email: string) {
  const c = await registrar({
    nome: "Ana Souza",
    email,
    senha: SENHA,
    cpf: "11144477735",
    biometria: bio,
    data_nascimento: "1990-05-04",
    celular: "11987654321",
    documento: null,
  });
  await concluirCadastro(c.etapa, bio);
}

describe("senha (demonstração)", () => {
  beforeEach(() => localStorage.clear());

  it("troca exige a senha atual e passa a valer a nova", async () => {
    await cadastrar("ana@exemplo.com");
    await expect(trocarSenha("errada-errada", NOVA, bio)).rejects.toThrow(/Senha atual/);
    await trocarSenha(SENHA, NOVA, bio);
    await expect(login({ email: "ana@exemplo.com", senha: SENHA })).rejects.toThrow(/senha/);
    await concluirLogin(await login({ email: "ana@exemplo.com", senha: NOVA }), bio);
  }, 20_000);

  it("recuperação pede o rosto completo e troca a senha", async () => {
    await cadastrar("ana@exemplo.com");
    const etapa = await iniciarRecuperacao("ana@exemplo.com", "1990-05-04");
    expect(etapa.desafio.modo).toBe("cadastro");
    await concluirRecuperacao(etapa, bio, NOVA);
    await concluirLogin(await login({ email: "ana@exemplo.com", senha: NOVA }), bio);
  }, 20_000);

  it("recuperação de conta que não existe não troca nada", async () => {
    const etapa = await iniciarRecuperacao("ninguem@exemplo.com", "1990-05-04");
    await expect(concluirRecuperacao(etapa, bio, NOVA)).rejects.toThrow(/identidade/);
  });
});
