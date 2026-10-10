import { beforeEach, expect, it, vi } from "vitest";
import { transferir, pagarFolha, pagarCobranca } from "./api";
import { post, requisitar } from "./http";
import { criarIntencaoPagamento } from "./intencao-pagamento";

vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  requisitar: vi.fn(),
  post: vi.fn(),
}));
beforeEach(() => vi.resetAllMocks());
it.each(["pix", "cobranca", "folha"])(
  "%s envia a chave da intenção sem recriá-la",
  async (tipo) => {
    const intencao = criarIntencaoPagamento();
    const primeira = intencao.preparar("destino:2|valor:10");
    const enviar = (chave: string) =>
      tipo === "pix"
        ? transferir({ destino: { numero: "2" }, valor: 10, idempotency_key: chave })
        : tipo === "cobranca"
          ? pagarCobranca("txid", chave, null)
          : pagarFolha([{ funcionario_id: 2, valor: "10.00" }], "Salário", undefined, chave);
    vi.mocked(requisitar).mockRejectedValueOnce(new TypeError("Rede caiu"));
    vi.mocked(post).mockRejectedValueOnce(new TypeError("Rede caiu"));
    await expect(enviar(primeira)).rejects.toThrow("Rede caiu");
    vi.mocked(requisitar).mockResolvedValue({
      status: 202,
      dados: { operacao_id: 1, mensagem: "Aprovação" },
    });
    vi.mocked(post).mockResolvedValue({ resultados: [{ situacao: "pago" }] });
    await enviar(intencao.preparar("destino:2|valor:10"));
    const corpos =
      tipo === "folha"
        ? vi.mocked(post).mock.calls.map((c) => c[1])
        : vi.mocked(requisitar).mock.calls.map((c) => c[2]);
    expect(corpos[0]).toMatchObject({ idempotency_key: primeira });
    expect(corpos[1]).toMatchObject({ idempotency_key: primeira });
    expect(intencao.preparar("destino:2|valor:20")).not.toBe(primeira);
    const segunda = intencao.preparar("destino:2|valor:20");
    intencao.concluir();
    expect(intencao.preparar("destino:2|valor:20")).not.toBe(segunda);
  },
);
it("usa entropia criptográfica quando randomUUID não está disponível", () => {
  vi.spyOn(globalThis.crypto, "randomUUID").mockImplementationOnce(
    () => "00000000-0000-4000-8000-000000000001",
  );
  expect(criarIntencaoPagamento().preparar("pix")).toBe("00000000-0000-4000-8000-000000000001");
  vi.restoreAllMocks();
  const cryptoSemUUID = { getRandomValues: crypto.getRandomValues.bind(crypto) };
  vi.stubGlobal("crypto", cryptoSemUUID);
  const chave = criarIntencaoPagamento().preparar("pix");
  expect(chave).toMatch(/^[a-f0-9]{48}$/);
  vi.unstubAllGlobals();
});
