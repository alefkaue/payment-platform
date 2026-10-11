import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("./dpop", () => ({ criarProva: vi.fn(async () => "prova") }));
const rede = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  rede.mockReset();
  vi.stubGlobal("fetch", rede);
  vi.stubEnv("VITE_API_URL", "https://api.teste");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it.each([502, 401])("HTML de erro %i não vaza nem quebra o tratamento", async (status) => {
  const http = await import("./http");
  rede.mockResolvedValue(new Response("<html>segredo interno</html>", { status }));
  await expect(http.get("/contas")).rejects.toMatchObject({ status, message: `Erro ${status}` });
});

it("resposta inválida de pagamento não repete a operação", async () => {
  const http = await import("./http");
  rede.mockResolvedValue(new Response("{incompleto", { status: 200 }));
  await expect(http.post("/pix", { valor: "1.00" })).rejects.toMatchObject({ status: 502 });
  expect(rede).toHaveBeenCalledTimes(1);
});

it("corpo interrompido vira erro tratado", async () => {
  const http = await import("./http");
  const resposta = new Response("{}");
  vi.spyOn(resposta, "text").mockRejectedValue(new Error("segredo"));
  rede.mockResolvedValue(resposta);
  await expect(http.get("/contas")).rejects.toMatchObject({ status: 502 });
});

it("resposta 204 continua aceita", async () => {
  const http = await import("./http");
  rede.mockResolvedValue(new Response(null, { status: 204 }));
  await expect(http.del("/chaves/1")).resolves.toBeNull();
});

it.each([
  "<html>erro</html>",
  "null",
  "{}",
  '{"access_token":2,"refresh_token":"x"}',
  '{"access_token":"x","refresh_token":" "}',
])("refresh inválido preserva sessão sem reenviar a operação: %s", async (corpo) => {
  const http = await import("./http");
  http.salvarTokens({ access_token: "original", refresh_token: "refresh-original" });
  rede
    .mockResolvedValueOnce(
      new Response("{}", { status: 401, headers: { "WWW-Authenticate": "Bearer" } }),
    )
    .mockResolvedValueOnce(new Response(corpo));
  await expect(http.post("/pix", { valor: "1.00" })).rejects.toMatchObject({ status: 503 });
  expect(http.refreshDaSessao()).toBe("refresh-original");
  expect(rede).toHaveBeenCalledTimes(2);
});

it("401 HTML após renovação recusada encerra sessão", async () => {
  const http = await import("./http");
  http.salvarTokens({ access_token: "a", refresh_token: "r" });
  rede
    .mockResolvedValueOnce(
      new Response("<html>erro</html>", { status: 401, headers: { "WWW-Authenticate": "Bearer" } }),
    )
    .mockResolvedValueOnce(new Response("{}", { status: 401 }));
  await expect(http.get("/contas")).rejects.toMatchObject({ status: 401 });
  expect(http.refreshDaSessao()).toBeUndefined();
});

it("trocar de conta durante refresh não reenvia pagamento pela nova conta", async () => {
  const http = await import("./http");
  http.salvarTokens({ access_token: "a", refresh_token: "r" });
  http.definirConta("conta-original");
  rede
    .mockResolvedValueOnce(
      new Response("{}", { status: 401, headers: { "WWW-Authenticate": "Bearer" } }),
    )
    .mockImplementationOnce(async () => {
      http.definirConta("outra-conta");
      return new Response(JSON.stringify({ access_token: "novo", refresh_token: "novo-refresh" }));
    })
    .mockResolvedValue(new Response("{}"));
  await expect(http.post("/pix", { valor: "1.00" })).rejects.toMatchObject({ status: 409 });
  expect(rede).toHaveBeenCalledTimes(2);
});

it("resposta atrasada da conta anterior não alimenta a conta atual", async () => {
  const http = await import("./http");
  http.definirConta("original");
  const resposta = new Response('{"saldo":"10.00"}');
  vi.spyOn(resposta, "text").mockImplementation(async () => {
    http.definirConta("outra");
    return '{"saldo":"10.00"}';
  });
  rede.mockResolvedValue(resposta);
  await expect(http.get("/saldo")).rejects.toMatchObject({ status: 409 });
});

it("trocar de conta e voltar também invalida a resposta pendente", async () => {
  const http = await import("./http");
  http.definirConta("original");
  rede.mockImplementation(async () => {
    http.definirConta("outra");
    http.definirConta("original");
    return new Response("{}");
  });
  await expect(http.get("/saldo")).rejects.toMatchObject({ status: 409 });
});

it("troca de conta durante assinatura cancela o envio", async () => {
  const http = await import("./http");
  const { criarProva } = await import("./dpop");
  http.definirConta("original");
  vi.mocked(criarProva).mockImplementationOnce(async () => {
    http.definirConta("outra");
    return "prova";
  });
  await expect(http.post("/pix", { valor: "1.00" })).rejects.toMatchObject({ status: 409 });
  expect(rede).not.toHaveBeenCalled();
});

it("logout durante assinatura cancela pagamento ainda não enviado", async () => {
  const http = await import("./http");
  const { criarProva } = await import("./dpop");
  http.salvarTokens({ access_token: "a", refresh_token: "r" });
  vi.mocked(criarProva).mockImplementationOnce(async () => {
    http.salvarTokens(null);
    return "prova";
  });
  await expect(http.post("/pix", { valor: "1.00" })).rejects.toMatchObject({ status: 409 });
  expect(rede).not.toHaveBeenCalled();
});
