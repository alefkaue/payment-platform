/**
 * Queda de sessão no cliente HTTP (SEGURANCA.md, item 7): quando o servidor recusa
 * a sessão e o refresh não a recupera, o app limpa tudo e avisa para ir ao login
 * com o motivo. 401 de biometria (sem WWW-Authenticate) não derruba ninguém.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./dpop", () => ({ criarProva: vi.fn(async () => "prova-dpop") }));

type Http = typeof import("./http");
const API = "https://api.teste";

function resposta(status: number, corpo: unknown, sessao = false): Response {
  const headers: Record<string, string> = { "Content-Type": "application/problem+json" };
  if (sessao) headers["WWW-Authenticate"] = "Bearer";
  return new Response(JSON.stringify(corpo), { status, headers });
}

async function carregar(): Promise<Http> {
  vi.resetModules();
  vi.stubEnv("VITE_API_URL", API);
  const http = await import("./http");
  http.salvarTokens({ access_token: "at", refresh_token: "rt" });
  return http;
}

describe("queda de sessão", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("logout limpa tokens e conta antes de a rede responder", async () => {
    const http = await carregar();
    http.definirConta("empresa");
    let concluir!: (r: Response) => void;
    fetchMock.mockImplementation(
      () =>
        new Promise((ok) => {
          concluir = ok;
        }),
    );
    const api = await import("./api");
    const saida = api.sair();
    expect(sessionStorage.getItem("payflow-tokens")).toBeNull();
    expect(sessionStorage.getItem("payflow-conta-numero")).toBeNull();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    http.salvarTokens({ access_token: "nova", refresh_token: "novo" });
    concluir(resposta(200, {}));
    await saida;
    expect(sessionStorage.getItem("payflow-tokens")).toContain("nova");
  });

  it("refresh atrasado não ressuscita sessão depois de logout", async () => {
    const http = await carregar();
    let concluir!: (r: Response) => void;
    fetchMock.mockResolvedValueOnce(resposta(401, {}, true)).mockImplementationOnce(
      () =>
        new Promise((ok) => {
          concluir = ok;
        }),
    );
    const pedido = http.get("/contas");
    const rejeicao = expect(pedido).rejects.toMatchObject({ status: 503 });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    http.salvarTokens(null);
    concluir(resposta(200, { access_token: "antigo", refresh_token: "antigo" }));
    await rejeicao;
    expect(sessionStorage.getItem("payflow-tokens")).toBeNull();
  });

  it("logout revoga a sessão mesmo sem tokens no sessionStorage", async () => {
    await carregar();
    sessionStorage.removeItem("payflow-tokens");
    fetchMock.mockResolvedValue(resposta(200, {}));
    const api = await import("./api");
    await api.sair();
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ refresh_token: "rt" }));
  });

  it("401 atrasado da pessoa anterior não encerra o novo login", async () => {
    const http = await carregar();
    const aviso = vi.fn();
    http.aoExpirarSessao(aviso);
    let concluir!: (r: Response) => void;
    fetchMock.mockImplementation(
      () =>
        new Promise((ok) => {
          concluir = ok;
        }),
    );
    const pedido = http.get("/contas");
    const rejeicao = expect(pedido).rejects.toMatchObject({ status: 409 });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    http.salvarTokens({ access_token: "nova", refresh_token: "novo" });
    concluir(resposta(401, {}, true));
    await rejeicao;
    expect(aviso).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("payflow-tokens")).toContain("nova");
  });

  it("refresh recusado: limpa a sessão e entrega o motivo do servidor ao login", async () => {
    const http = await carregar();
    const avisos: string[] = [];
    http.aoExpirarSessao((m) => avisos.push(m));
    fetchMock
      .mockResolvedValueOnce(resposta(401, { detail: "Token inválido ou expirado." }, true))
      .mockResolvedValueOnce(
        resposta(401, { detail: "Sessão encerrada por inatividade. Entre de novo." }),
      );

    await expect(http.get("/contas")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`${API}/auth/refresh`);
    expect(avisos).toEqual(["Sessão encerrada por inatividade. Entre de novo."]);
    expect(sessionStorage.getItem("payflow-tokens")).toBeNull();
    expect(http.motivoSaida()).toBe("Sessão encerrada por inatividade. Entre de novo.");
    expect(http.motivoSaida()).toBeNull(); // lido uma vez só
  });

  it("refresh ok: repete a requisição e a sessão continua", async () => {
    const http = await carregar();
    const aviso = vi.fn();
    http.aoExpirarSessao(aviso);
    fetchMock
      .mockResolvedValueOnce(resposta(401, { detail: "Token inválido ou expirado." }, true))
      .mockResolvedValueOnce(resposta(200, { access_token: "at2", refresh_token: "rt2" }))
      .mockResolvedValueOnce(resposta(200, [{ numero: "1" }]));

    await expect(http.get("/contas")).resolves.toEqual([{ numero: "1" }]);
    const auth = (fetchMock.mock.calls[2]?.[1]?.headers as Record<string, string>)["Authorization"];
    expect(auth).toBe("Bearer at2");
    expect(aviso).not.toHaveBeenCalled();
  });

  it("401 de biometria (sem WWW-Authenticate) não renova nem derruba", async () => {
    const http = await carregar();
    const aviso = vi.fn();
    http.aoExpirarSessao(aviso);
    fetchMock.mockResolvedValueOnce(
      resposta(401, { detail: "Rosto não corresponde ao titular da conta." }),
    );

    await expect(http.post("/pagamentos/transferir", {})).rejects.toThrow("Rosto não corresponde");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(aviso).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("payflow-tokens")).not.toBeNull();
  });

  it("servidor fora do ar no refresh: não desloga", async () => {
    const http = await carregar();
    const aviso = vi.fn();
    http.aoExpirarSessao(aviso);
    fetchMock
      .mockResolvedValueOnce(resposta(401, { detail: "Token inválido ou expirado." }, true))
      .mockResolvedValueOnce(resposta(503, { detail: "Indisponível" }));

    await expect(http.get("/contas")).rejects.toMatchObject({ status: 503 });
    expect(aviso).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("payflow-tokens")).not.toBeNull();
  });

  it("401 no login (senha errada) não é queda de sessão", async () => {
    const http = await carregar();
    const aviso = vi.fn();
    http.aoExpirarSessao(aviso);
    fetchMock.mockResolvedValueOnce(resposta(401, { detail: "Credenciais inválidas." }, true));

    await expect(http.post("/auth/login", {})).rejects.toThrow("Credenciais inválidas.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(aviso).not.toHaveBeenCalled();
  });
});

describe("renovação em paralelo (revisão do Claude sobre o C1-02)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("um refresh feito por outra requisição não descarta a resposta de um Pix já executado", async () => {
    const http = await carregar();
    let concluirPix!: (r: Response) => void;
    fetchMock.mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("/pagamentos/transferir"))
        return new Promise<Response>((ok) => {
          concluirPix = ok;
        });
      if (u.endsWith("/auth/refresh"))
        return resposta(200, { access_token: "at2", refresh_token: "rt2" });
      // A primeira chamada de /contas encontra o token vencido; depois do refresh, passa.
      return fetchMock.mock.calls.filter((c) => String(c[0]).endsWith("/contas")).length === 1
        ? resposta(401, {}, true)
        : resposta(200, []);
    });
    const pix = http.post<{ id: number }>("/pagamentos/transferir", { valor: "10.00" });
    await vi.waitFor(() => expect(concluirPix).toBeTypeOf("function"));
    await http.get("/contas"); // renova o token no meio do Pix
    concluirPix(resposta(200, { id: 42 }));
    await expect(pix).resolves.toEqual({ id: 42 });
  });
});
