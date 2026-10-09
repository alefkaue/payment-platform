/**
 * Modo demonstração (sem VITE_API_URL): cadastro, login, chaves Pix e Pix entre
 * contas diferentes no mesmo navegador, com as regras do backend.
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  apuracaoPJ,
  consultarDestino,
  equipe,
  listarFaturas,
  notificacoes,
  pendentes,
  concluirCadastro,
  concluirLogin,
  criarChave,
  depositar,
  login,
  minhaConta,
  minhasChaves,
  registrar,
  removerChave,
  transacoes,
  transferir,
} from "./api";

const bio = { desafio_id: "demo", quadros: [] };
const dados = { data_nascimento: "1990-05-04", celular: "11987654321", documento: null };
const SENHA = "Cofre-Astro#2026";

/** Login em 2 etapas: senha -> rosto (na demonstração o rosto é simulado). */
async function entrar(email: string, senha = SENHA) {
  return concluirLogin(await login({ email, senha }), bio);
}

async function cadastrar(nome: string, email: string, cpf: string) {
  const c = await registrar({ nome, email, senha: SENHA, cpf, biometria: bio, ...dados });
  return (await concluirCadastro(c.etapa, bio)).resposta;
}

describe("modo demonstração", () => {
  beforeEach(() => localStorage.clear());

  it("o cadastro guarda o e-mail e o CPF de quem se cadastrou (não a Marina)", async () => {
    const r = await cadastrar("Ana Souza", "Ana@Exemplo.com", "111.444.777-35");
    expect(r.pessoa).toEqual({ nome: "Ana Souza", email: "ana@exemplo.com", cpf: "11144477735" });
    const de_novo = await entrar("ana@exemplo.com");
    expect(de_novo.pessoa?.email).toBe("ana@exemplo.com");
    expect(de_novo.conta.nome).toBe("Ana Souza");
    await expect(login({ email: "ana@exemplo.com", senha: "errada123" })).rejects.toThrow(
      /senha incorretos/,
    );
    await expect(cadastrar("Outra", "ana@exemplo.com", "52998224725")).rejects.toThrow(/e-mail/);
  }, 20_000);

  it("cadastra chaves e paga por chave entre duas contas", async () => {
    await cadastrar("Beatriz Lima", "bia@exemplo.com", "11144477735");
    await criarChave("cpf");
    await criarChave("email", "bia.pix@exemplo.com");
    await criarChave("celular", "(21) 99999-8888");
    const aleatoria = await criarChave("aleatoria");
    await expect(criarChave("email")).rejects.toThrow(/E-mail inválido/);
    await expect(criarChave("cnpj")).rejects.toThrow(/CNPJ só para conta de empresa/);
    await expect(criarChave("email", "BIA.PIX@exemplo.com")).rejects.toThrow(/já está cadastrada/);
    expect((await minhasChaves()).map((k) => k.tipo).sort()).toEqual([
      "aleatoria",
      "celular",
      "cpf",
      "email",
    ]);

    const ana = await cadastrar("Ana Souza", "ana@exemplo.com", "39053344705");
    expect(await minhasChaves()).toEqual([]); // as chaves são da conta da Beatriz
    await depositar({ valor: 100 });
    for (const chave of [
      "111.444.777-35",
      "bia.pix@exemplo.com",
      "21 99999-8888",
      aleatoria.valor,
    ]) {
      const d = await consultarDestino(chave);
      expect(d.nome).toBe("Beatriz Lima");
      await transferir({ destino: d.destino!, valor: 10, descricao: "" });
    }
    expect((await minhaConta()).saldo).toBe(60);
    expect(ana.conta.nome).toBe("Ana Souza");

    await entrar("bia@exemplo.com");
    expect((await minhaConta()).saldo).toBe(40);
    const ts = await transacoes();
    expect(ts).toHaveLength(4);
    expect(ts[0]!.descricao).toBe("Pix de Ana Souza");
  }, 30_000);

  it("remove chave e libera para outra conta; chave inexistente dá erro", async () => {
    await cadastrar("Beatriz Lima", "bia@exemplo.com", "11144477735");
    const k = await criarChave("email", "troca@exemplo.com");
    await removerChave(k.id);
    await cadastrar("Ana Souza", "ana@exemplo.com", "39053344705");
    await criarChave("email", "troca@exemplo.com");
    expect((await consultarDestino("troca@exemplo.com")).nome).toBe("Ana Souza");
    await expect(consultarDestino("ninguem@exemplo.com")).rejects.toThrow(/não encontrada/);
  }, 20_000);

  it("e-mail desconhecido continua entrando na conta da demonstração (Marina)", async () => {
    const etapa = await login({ email: "qualquer@exemplo.com", senha: "x" });
    expect(etapa.desafio.passos.map((p) => p.id)).toEqual(["piscar3"]); // 2º fator: o rosto
    const r = await concluirLogin(etapa, bio);
    expect(r.conta.nome).toBe("Marina Alves");
    expect(r.contas.map((c) => c.tipo)).toEqual(["PF", "PJ"]);
    expect((await consultarDestino("marina@email.com")).nome).toBe("Marina Alves");
  }, 20_000);

  it("empresa recém-criada começa vazia (não herda dados da Rodoforte)", async () => {
    const empresa = {
      cnpj: "11222333000181",
      nome_fantasia: "Dias Peças",
      porte: "PME" as const,
      regime_apuracao: "simples" as const,
    };
    const c = await registrar({
      nome: "Carla Dias",
      email: "carla@exemplo.com",
      senha: SENHA,
      cpf: "39053344705",
      biometria: bio,
      ...dados,
      empresa,
    });
    const r = (await concluirCadastro(c.etapa, bio, empresa)).resposta;
    const pj = r.contas.find((c) => c.tipo === "PJ")!;
    expect(pj.cnpj).toBe("11.222.333/0001-81");
    const { selecionarConta } = await import("./api");
    selecionarConta(pj);
    expect((await equipe()).map((m) => m.email)).toEqual(["carla@exemplo.com"]);
    expect(await pendentes()).toEqual([]);
    expect(await listarFaturas()).toEqual([]);
    expect((await apuracaoPJ()).faturamento).toBe(0);
    expect((await notificacoes()).map((n) => n.titulo)).toEqual(["Boas-vindas à Astro"]);
    await criarChave("cnpj");
    expect((await consultarDestino("11.222.333/0001-81")).nome).toBe("Dias Peças");
  }, 20_000);
});
