import { beforeEach, expect, it, vi } from "vitest";
import { registrarEEntrar } from "./api";
import { get, post, salvarTokens } from "./http";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  get: vi.fn(),
  post: vi.fn(),
  salvarTokens: vi.fn(),
  definirConta: vi.fn(),
}));
const pf = {
  carteira_id: 15,
  titular_tipo: "PF",
  nome: "Pessoa Nova",
  documento: "12345678909",
  agencia: "0001",
  numero: "15",
  saldo: "0.00",
  saldo_bloqueado: "0.00",
};
const p = {
  nome: "Pessoa Nova",
  email: "nova@ex.com",
  senha: "Cofre-Astro#2026",
  cpf: "12345678909",
  data_nascimento: "1995-01-01",
  celular: "11987654321",
  documento: null,
  biometria: { desafio_id: "cadastro", quadros: ["foto1", "foto2"] },
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(get).mockResolvedValue({ nome: p.nome, email: p.email, contas: [pf] });
  vi.mocked(post).mockResolvedValue({
    conta: { kyc: { status: "pendente", motivos: [] } },
    tokens: { access_token: "access", refresh_token: "refresh" },
  });
});
it("entra com a prova do cadastro sem pedir outro login ou desafio", async () => {
  const r = await registrarEEntrar(p);
  expect(r.resposta.conta.carteira_id).toBe(15);
  expect(post).toHaveBeenCalledTimes(1);
  expect(post).toHaveBeenCalledWith(
    "/usuarios/cadastro-sessao",
    expect.objectContaining({ biometria: p.biometria }),
  );
  expect(salvarTokens).toHaveBeenLastCalledWith({
    access_token: "access",
    refresh_token: "refresh",
  });
});
it("se a empresa falhar, conserva o acesso à conta pessoal", async () => {
  // A primeira chamada cria a sessão; somente a abertura da PJ falha.
  vi.mocked(post)
    .mockReset()
    .mockResolvedValueOnce({ conta: {}, tokens: { access_token: "a", refresh_token: "r" } })
    .mockRejectedValueOnce(new Error("CNPJ recusado"));
  const r = await registrarEEntrar({
    ...p,
    empresa: {
      cnpj: "12345678000199",
      nome_fantasia: "Loja",
      porte: "PME",
      regime_apuracao: "regular",
    },
  });
  expect(r.erroEmpresa).toBe("CNPJ recusado");
  expect(r.resposta.conta.carteira_id).toBe(15);
});
it("falha facial não carrega conta nem salva sessão", async () => {
  vi.mocked(post).mockRejectedValueOnce(new Error("Prova de vida recusada"));
  await expect(registrarEEntrar(p)).rejects.toThrow("Prova de vida recusada");
  expect(get).not.toHaveBeenCalled();
  expect(salvarTokens).toHaveBeenCalledWith(null);
  expect(salvarTokens).toHaveBeenCalledTimes(1);
});
