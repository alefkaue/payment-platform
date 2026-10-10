import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "@/routes/_app.auditoria";
import { auditoriaEmpresa } from "@/lib/api";

const auth = vi.hoisted(() => ({ conta: { id: 77, tipo: "PJ", papel: "admin" } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  auditoriaEmpresa: vi.fn(),
}));
beforeEach(() => {
  auth.conta = { id: 77, tipo: "PJ", papel: "admin" };
  vi.mocked(auditoriaEmpresa).mockReset().mockResolvedValue([]);
});
afterEach(cleanup);
function abrir() {
  const Component = Route.options.component!;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Component />
    </QueryClientProvider>,
  );
}
it.each(["operador", "consulta", ""])("não consulta a API para papel %s", (papel) => {
  auth.conta.papel = papel;
  abrir();
  expect(
    screen.getByText("Só administradores e aprovadores veem a trilha da empresa."),
  ).toBeTruthy();
  expect(auditoriaEmpresa).not.toHaveBeenCalled();
});
it("não consulta a API para PF", () => {
  auth.conta.tipo = "PF";
  abrir();
  expect(screen.getByText("Só para empresas")).toBeTruthy();
  expect(auditoriaEmpresa).not.toHaveBeenCalled();
});
it.each(["admin", "aprovador"])("carrega de 50 até 200 para %s", async (papel) => {
  auth.conta.papel = papel;
  abrir();
  await waitFor(() => expect(auditoriaEmpresa).toHaveBeenLastCalledWith(50));
  for (const limite of [100, 150, 200]) {
    const botao = await screen.findByRole("button", { name: "Carregar mais" });
    await waitFor(() => expect(botao.hasAttribute("disabled")).toBe(false));
    fireEvent.click(botao);
    await waitFor(() => expect(auditoriaEmpresa).toHaveBeenLastCalledWith(limite));
  }
  expect(screen.queryByRole("button", { name: "Carregar mais" })).toBeNull();
});
