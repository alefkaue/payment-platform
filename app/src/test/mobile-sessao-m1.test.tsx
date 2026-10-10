import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const eventos = vi.hoisted(() => new Map<string, (estado: { isActive: boolean }) => void>());
vi.mock("@capacitor/core", async (original) => ({
  ...(await original<typeof import("@capacitor/core")>()),
  Capacitor: { isNativePlatform: () => true },
}));
vi.mock("@/lib/dpop", () => ({ criarProva: async () => "prova-de-teste" }));
vi.mock("@capacitor/app", () => ({
  App: {
    addListener: vi.fn(async (nome: string, fn: (estado: { isActive: boolean }) => void) => {
      eventos.set(nome, fn);
      return { remove: vi.fn() };
    }),
    exitApp: vi.fn(),
  },
}));
vi.mock("@capacitor/network", () => ({
  Network: {
    addListener: vi.fn(async () => ({ remove: vi.fn() })),
    getStatus: async () => ({ connected: true }),
  },
}));
vi.mock("@capacitor/keyboard", () => ({
  Keyboard: { addListener: vi.fn(async () => ({ remove: vi.fn() })) },
}));
vi.mock("@capacitor/status-bar", () => ({
  Style: { Dark: "DARK" },
  StatusBar: {
    setBackgroundColor: async () => {},
    setStyle: async () => {},
  },
}));
const router = {
  state: { location: { pathname: "/inicio" } },
  history: { canGoBack: () => true, back: vi.fn() },
  navigate: vi.fn(),
};
vi.mock("@tanstack/react-router", () => ({ useRouter: () => router }));

beforeEach(() => {
  vi.resetModules();
  eventos.clear();
  sessionStorage.clear();
  vi.stubEnv("VITE_API_URL", "https://api.teste");
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it("tokens e conta ficam só em memória no Android", async () => {
  sessionStorage.setItem(
    "payflow-tokens",
    JSON.stringify({ access_token: "antigo", refresh_token: "antigo" }),
  );
  const http = await import("@/lib/http");
  expect(http.refreshDaSessao()).toBeUndefined();
  http.salvarTokens({ access_token: "teste", refresh_token: "refresh-teste" });
  http.definirConta("123");
  expect(http.refreshDaSessao()).toBe("refresh-teste");
  expect(sessionStorage.getItem("payflow-tokens")).toBeNull();
  expect(sessionStorage.getItem("payflow-conta-numero")).toBeNull();
});

it("ao retomar, a recusa por inatividade dispara o fluxo existente de sessão expirada", async () => {
  const fetchMock = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Sessão expirada" }), {
        status: 401,
        headers: { "WWW-Authenticate": "Bearer" },
      }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Sessão expirada por inatividade" }), { status: 401 }),
    );
  vi.stubGlobal("fetch", fetchMock);
  const http = await import("@/lib/http");
  http.salvarTokens({ access_token: "teste", refresh_token: "refresh-teste" });
  const expirou = vi.fn();
  const remover = http.aoExpirarSessao(expirou);
  const { AmbienteAndroid } = await import("@/lib/mobile");
  render(<AmbienteAndroid />);
  await waitFor(() => expect(eventos.has("appStateChange")).toBe(true));
  act(() => eventos.get("appStateChange")!({ isActive: false }));
  expect(fetchMock).not.toHaveBeenCalled();
  act(() => eventos.get("appStateChange")!({ isActive: true }));
  await waitFor(() => expect(expirou).toHaveBeenCalledWith("Sessão expirada por inatividade"));
  expect(http.refreshDaSessao()).toBeUndefined();
  expect(http.motivoSaida()).toBe("Sessão expirada por inatividade");
  remover();
});
