/** Tela de transferência: confirma com senha (+ código do autenticador acima de R$ 5.000). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "@/routes/_app.transferir";
import { ApiError, consultarDestino, temTotp, transferir } from "@/lib/api";

const navegar = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ conta: { tipo: "PF", carteira_id: 1, numero: "1" } }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => navegar,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  consultarDestino: vi.fn(),
  transferir: vi.fn(),
  temTotp: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(consultarDestino).mockResolvedValue({
    carteira_id: 2,
    nome: "Ana",
    tipo: "PF",
    destino: { numero: "2" },
  });
  vi.mocked(transferir).mockReset();
  vi.mocked(temTotp).mockResolvedValue(true);
  navegar.mockReset();
});
afterEach(cleanup);

async function revisar(valor: string) {
  const Component = Route.options.component!;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Component />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("Chave Pix ou conta"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: valor } });
  fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirmar transferência" }));
  return screen.findByRole("dialog", { name: "Confirme a transferência" });
}

it("até R$ 5.000 pede só a senha e manda a confirmação, sem câmera", async () => {
  vi.mocked(transferir).mockResolvedValue({
    tipo: "transacao",
    transacao: { id: 9 } as never,
  });
  await revisar("100,00");
  expect(screen.queryByLabelText("Código do app autenticador")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Digite a senha");
  expect(transferir).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Senha da conta"), { target: { value: "s3nh@" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  await waitFor(() =>
    expect(transferir).toHaveBeenCalledWith(
      expect.objectContaining({ valor: 100, confirmacao: { senha: "s3nh@" } }),
    ),
  );
  await waitFor(() =>
    expect(navegar).toHaveBeenCalledWith({ to: "/comprovante/$id", params: { id: "9" } }),
  );
});

it("acima de R$ 5.000 pede o código; erro deixa a janela aberta e limpa o código", async () => {
  vi.mocked(transferir).mockRejectedValueOnce(
    new ApiError("Código de verificação inválido ou já utilizado.", 401),
  );
  await revisar("6000,00");
  fireEvent.change(screen.getByLabelText("Senha da conta"), { target: { value: "s3nh@" } });
  const codigo = screen.getByLabelText("Código do app autenticador");
  fireEvent.change(codigo, { target: { value: "12a3456" } });
  expect(codigo).toHaveValue("123456");
  fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("já utilizado");
  expect(transferir).toHaveBeenCalledWith(
    expect.objectContaining({ confirmacao: { senha: "s3nh@", codigo_totp: "123456" } }),
  );
  expect(codigo).toHaveValue("");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("sem TOTP ativo, avisa e leva para ativar em vez de tentar pagar", async () => {
  vi.mocked(temTotp).mockResolvedValue(false);
  await revisar("6000,00");
  expect(await screen.findByRole("link", { name: "Ativar agora" })).toHaveAttribute(
    "href",
    "/seguranca",
  );
  expect(screen.getByRole("button", { name: "Confirmar" })).toBeDisabled();
});

it("se o servidor pedir o 2º fator, a janela passa a pedir o código", async () => {
  vi.mocked(transferir).mockRejectedValueOnce(
    new ApiError("Ative a verificação em duas etapas (TOTP) para pagamentos acima do limite.", 403),
  );
  await revisar("100,00");
  fireEvent.change(screen.getByLabelText("Senha da conta"), { target: { value: "s3nh@" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  expect(await screen.findByLabelText("Código do app autenticador")).toBeInTheDocument();
});
