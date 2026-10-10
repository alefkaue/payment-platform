import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/lib/auth";
import type { Conta } from "@/lib/types";
import type { ReactNode } from "react";

const estado = vi.hoisted(() => ({ expirar: () => {} }));
vi.mock("@/lib/api", () => ({ sair: vi.fn(async () => {}), selecionarConta: vi.fn() }));
vi.mock("@/lib/http", () => ({
  aoExpirarSessao: (fn: () => void) => {
    estado.expirar = fn;
    return () => {};
  },
}));
afterEach(() => {
  cleanup();
  sessionStorage.clear();
});
const conta: Conta = {
  id: 1,
  carteira_id: 1,
  numero: "1",
  nome: "Pessoa",
  tipo: "PF",
  saldo: 0,
  pontos: 0,
};

it.each(["sair", "expirar", "trocar", "entrar"])("limpa cache privado ao %s", (acao) => {
  const qc = new QueryClient();
  const { result } = renderHook(useAuth, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    ),
  });
  act(() =>
    result.current.entrar({
      conta,
      contas: [conta],
      pessoa: { nome: "Pessoa", email: "p@ex.com", cpf: "123" },
    }),
  );
  qc.setQueryData(["extrato"], { privado: "segredo" });
  act(() => {
    if (acao === "expirar") estado.expirar();
    else if (acao === "trocar") result.current.trocarConta({ ...conta, numero: "2" });
    else if (acao === "entrar") result.current.entrar({ conta, contas: [conta] });
    else result.current.sair();
  });
  expect(qc.getQueryCache().getAll()).toHaveLength(0);
  if (acao === "sair" || acao === "expirar") {
    expect(result.current.pessoa).toBeNull();
    expect(result.current.conta).toBeNull();
    expect(sessionStorage.getItem("payflow-session")).toBeNull();
  }
});
