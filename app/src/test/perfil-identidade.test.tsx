import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "@/routes/_app.perfil";
import { minhaVerificacao, reenviarDocumento } from "@/lib/api";
import type { KycResultado } from "@/lib/types";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ conta: { tipo: "PF", numero: "teste" }, pessoa: {}, sair: vi.fn() }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/lib/api", () => ({
  minhaConta: vi.fn().mockResolvedValue({ nome: "Ana" }),
  aparelhoAtual: vi.fn().mockResolvedValue({ confiavel: true }),
  minhaVerificacao: vi.fn(),
  reenviarDocumento: vi.fn(),
}));
vi.mock("@/components/payflow/documento", () => ({
  CampoDocumento: ({ rotulo, onChange }: { rotulo: string; onChange: (valor: string) => void }) => (
    <button type="button" onClick={() => onChange("foto")}>
      {rotulo}
    </button>
  ),
}));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function abrir(status: KycResultado["status"] | null, motivos: string[] = []) {
  vi.mocked(minhaVerificacao).mockResolvedValue({
    status,
    caso: { id: 1, status: "em_analise", motivos },
  });
  const Component = Route.options.component!;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Component />
    </QueryClientProvider>,
  );
}

it.each([
  ["aprovado", "Verificada", "text-pos"],
  ["em_analise", "Em análise", "text-pending"],
  ["pendente", "Pendente", "text-pending"],
  ["reprovado", "Recusada", "text-errt"],
  [null, "Pendente", "text-pending"],
] as const)("mostra status %s com cor e ação corretas", async (status, texto, cor) => {
  abrir(status);
  await waitFor(() => expect(screen.getAllByText(texto).length).toBeGreaterThan(0));
  expect(screen.getAllByText(texto).every((el) => el.classList.contains(cor))).toBe(true);
  expect(!!screen.queryByRole("button", { name: "Enviar documento" })).toBe(status !== "aprovado");
});

it("simplifica os motivos e atualiza o status após enviar frente e verso", async () => {
  abrir("pendente", [
    "Texto do documento não conferido automaticamente (sem OCR): análise humana.",
  ]);
  expect(
    await screen.findByText("Precisamos analisar os dados do documento com mais cuidado."),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Enviar documento" }));
  const enviar = screen.getByRole("button", { name: "Enviar para verificação" });
  expect(enviar.hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "CNH — frente" }));
  expect(enviar.hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "CNH — verso" }));
  vi.mocked(reenviarDocumento).mockResolvedValue({ status: "em_analise", motivos: [], caso_id: 2 });
  vi.mocked(minhaVerificacao).mockResolvedValue({ status: "em_analise", caso: null });
  fireEvent.click(enviar);
  await waitFor(() =>
    expect(reenviarDocumento).toHaveBeenCalledWith(
      { tipo: "cnh", frente: "foto", verso: "foto" },
      expect.anything(),
    ),
  );
  await waitFor(() => expect(screen.getAllByText("Em análise")).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Enviar para verificação" })).toBeNull();
});
