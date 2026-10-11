import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("./dpop", () => ({ criarProva: vi.fn(async () => "prova"), atestacaoDoAparelho: vi.fn() }));
const rede = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.stubEnv("VITE_API_URL", "https://api.teste");
  vi.stubGlobal("fetch", rede);
  rede.mockReset();
  sessionStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it("transferência não usa conta escolhida durante atraso artificial", async () => {
  const http = await import("./http");
  const api = await import("./api");
  http.definirConta("original");
  rede.mockResolvedValue(
    new Response(JSON.stringify({ operacao_id: 1, mensagem: "pendente" }), { status: 202 }),
  );
  const pedido = api.transferir({
    destino: { numero: "12345678-9" },
    valor: 1,
    idempotency_key: "teste",
  });
  const resultado = pedido.then(
    () => null,
    (erro: unknown) => erro,
  );
  http.definirConta("outra");
  await vi.advanceTimersByTimeAsync(1000);
  expect(await resultado).toMatchObject({ status: 409 });
  expect(rede).not.toHaveBeenCalled();
});

it("depósito não usa outra conta entre a consulta e o envio", async () => {
  const http = await import("./http");
  const api = await import("./api");
  http.definirConta("original");
  vi.spyOn(http, "get").mockImplementationOnce(async <T>() => {
    http.definirConta("outra");
    return { carteira_id: 1 } as T;
  });
  await expect(api.depositar({ valor: 1 })).rejects.toMatchObject({ status: 409 });
  expect(rede).not.toHaveBeenCalled();
});

it("extrato não consulta transações em outra conta após obter a carteira", async () => {
  const http = await import("./http");
  const api = await import("./api");
  http.definirConta("original");
  vi.spyOn(http, "get").mockImplementationOnce(async <T>() => {
    http.definirConta("outra");
    return { carteira_id: 1 } as T;
  });
  await expect(api.transacoes()).rejects.toMatchObject({ status: 409 });
  expect(rede).not.toHaveBeenCalled();
});
