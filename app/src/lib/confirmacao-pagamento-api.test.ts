/** Modo API: o corpo de cada pagamento leva senha/codigo_totp, e nunca mais o rosto. */
import { beforeEach, expect, it, vi } from "vitest";
import {
  comprarProduto,
  confirmarTotp,
  decidirPendente,
  iniciarTotp,
  pagarCobranca,
  pagarFolha,
  repetirPendente,
  temTotp,
  transferir,
} from "./api";
import { get, post, requisitar } from "./http";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  requisitar: vi.fn(),
  post: vi.fn(),
  get: vi.fn(),
}));

const conf = { senha: "minha-senha", codigo_totp: " 123456 " };
const pendente = {
  id: 7,
  tipo: "folha",
  valor: "100.00",
  status: "pendente",
  criado_em: "2026-10-16T12:00:00Z",
  criado_por: "Ana",
  aprovacoes_necessarias: 1,
  aprovacoes: [],
  payload: {},
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(requisitar).mockResolvedValue({
    status: 202,
    dados: { operacao_id: 1, mensagem: "Aprovação" },
  });
});

it.each(["pix", "cobranca"])("%s envia senha e código, sem biometria", async (tipo) => {
  if (tipo === "pix")
    await transferir({ destino: { numero: "2" }, valor: 6000, confirmacao: conf });
  else await pagarCobranca("txid", "chave-123456", conf);
  const corpo = vi.mocked(requisitar).mock.calls[0]![2] as Record<string, unknown>;
  expect(corpo).toMatchObject({ senha: "minha-senha", codigo_totp: "123456" });
  expect(corpo).not.toHaveProperty("biometria");
});

it("sem código, o campo nem vai (o servidor decide se pede)", async () => {
  await transferir({ destino: { numero: "2" }, valor: 10, confirmacao: { senha: "s" } });
  const corpo = vi.mocked(requisitar).mock.calls[0]![2] as Record<string, unknown>;
  expect(corpo).toMatchObject({ senha: "s" });
  expect(corpo).not.toHaveProperty("codigo_totp");
});

it("folha, aprovação, repetição e compra levam a confirmação; recusar não leva", async () => {
  vi.mocked(post).mockResolvedValue({ ...pendente, transacao: { origem: { carteira_id: 1 } } });
  await pagarFolha([{ funcionario_id: 2, valor: "10.00" }], "Salário", conf, "chave-123456");
  expect(vi.mocked(post).mock.calls[0]![1]).toMatchObject({
    senha: "minha-senha",
    codigo_totp: "123456",
  });
  await decidirPendente(7, true, conf);
  expect(post).toHaveBeenLastCalledWith("/pagamentos/pendentes/7/decidir", {
    aprovar: true,
    senha: "minha-senha",
    codigo_totp: "123456",
  });
  await decidirPendente(7, false, conf);
  expect(post).toHaveBeenLastCalledWith("/pagamentos/pendentes/7/decidir", { aprovar: false });
  await repetirPendente(7, { senha: "minha-senha" });
  expect(post).toHaveBeenLastCalledWith("/pagamentos/pendentes/7/repetir", {
    senha: "minha-senha",
  });
  vi.mocked(post).mockResolvedValueOnce({
    transacao: {
      id: 1,
      origem: { carteira_id: 1 },
      destino: { carteira_id: 2, tipo: "PJ" },
      valor_bruto: "10.00",
      cbs: "0",
      ibs: "0",
      liquido: "10.00",
      status: "concluida",
      criado_em: "2026-10-16T12:00:00Z",
    },
  });
  await comprarProduto({ produto_id: 3, confirmacao: { senha: "minha-senha" } });
  expect(post).toHaveBeenLastCalledWith("/loja/produtos/3/comprar", { senha: "minha-senha" });
});

it("ativação do TOTP usa /auth/totp e /auth/totp/confirmar; status vem de /auth/eu", async () => {
  vi.mocked(get).mockResolvedValue({ tem_totp: true });
  expect(await temTotp()).toBe(true);
  expect(get).toHaveBeenCalledWith("/auth/eu");
  vi.mocked(post).mockResolvedValueOnce({ segredo: "ABC", uri: "otpauth://totp/x" });
  expect(await iniciarTotp()).toEqual({ segredo: "ABC", uri: "otpauth://totp/x" });
  expect(post).toHaveBeenLastCalledWith("/auth/totp");
  vi.mocked(post).mockResolvedValueOnce(null);
  await confirmarTotp("123 456");
  expect(post).toHaveBeenLastCalledWith("/auth/totp/confirmar", { codigo: "123456" });
  await expect(confirmarTotp("12")).rejects.toMatchObject({ status: 400 });
});
