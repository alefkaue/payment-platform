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
