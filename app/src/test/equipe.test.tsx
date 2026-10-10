import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "@/routes/_app.equipe";
import { alterarVinculo, equipe, politicaEmpresa } from "@/lib/api";
import type { MembroEquipe, ProvaBiometrica } from "@/lib/types";

const auth = vi.hoisted(() => ({
  conta: { tipo: "PJ", papel: "admin", numero: "teste" },
  trocarConta: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  Navigate: () => null,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  MODO_API: true,
  equipe: vi.fn(),
  politicaEmpresa: vi.fn(),
  alterarVinculo: vi.fn(),
}));
vi.mock("@/components/payflow/liveness", () => ({
  LivenessCheck: ({ onSuccess }: { onSuccess: (prova: ProvaBiometrica) => void }) => (
    <button onClick={() => onSuccess({ desafio_id: "teste", quadros: [] })}>Confirmar rosto</button>
  ),
}));
const membro: MembroEquipe = {
  id: 7,
  nome: "Ana",
  email: null,
  papel: "operador",
  alcada: 100,
  status: "ativo",
  ativo: true,
};
beforeEach(() => {
  auth.conta.papel = "admin";
  vi.mocked(equipe).mockResolvedValue([{ ...membro }]);
  vi.mocked(politicaEmpresa).mockResolvedValue({
    porte: "GRANDE",
    max_usuarios: 500,
    papeis_convidaveis: ["admin", "aprovador", "operador", "consulta"],
    operador_exige_alcada: true,
    quatro_olhos_acesso: true,
    duas_aprovacoes_acima: 250000,
    resumo: "Política da empresa",
  });
  vi.mocked(alterarVinculo).mockReset();
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
it("quem não administra não vê Editar", async () => {
  auth.conta.papel = "aprovador";
  abrir();
  await screen.findByText("Ana");
  expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
});
it("redução salva sem rosto e mostra erro do servidor", async () => {
  vi.mocked(alterarVinculo).mockRejectedValue(new Error("Alteração recusada pelo servidor."));
  abrir();
  fireEvent.click(await screen.findByRole("button", { name: "Editar" }));
  fireEvent.change(screen.getByLabelText("Alçada por operação (R$)"), {
    target: { value: "50,00" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Alteração recusada pelo servidor.")).toBeTruthy();
  expect(screen.queryByText("Confirmar rosto")).toBeNull();
  expect(alterarVinculo).toHaveBeenCalledWith(7, { papel: "operador", alcada: "50.00" }, undefined);
});
it("aumento diário pede rosto antes do PATCH e mostra aprovação pendente", async () => {
  vi.mocked(alterarVinculo).mockResolvedValue({
    ...membro,
    aguardando_aprovacao: true,
    operacao_id: 42,
  });
  abrir();
  fireEvent.click(await screen.findByRole("button", { name: "Editar" }));
  expect(screen.queryByLabelText("Sem limite")).toBeNull();
  fireEvent.change(screen.getByLabelText("Alçada diária (R$)"), { target: { value: "200,00" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await screen.findByText("Confirmar rosto");
  expect(alterarVinculo).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Confirmar rosto"));
  await waitFor(() =>
    expect(alterarVinculo).toHaveBeenCalledWith(
      7,
      { papel: "operador", alcada: "100.00", alcada_diaria: "200.00" },
      { desafio_id: "teste", quadros: [] },
    ),
  );
  expect(await screen.findByText("Enviado para aprovação de outro administrador")).toBeTruthy();
});
