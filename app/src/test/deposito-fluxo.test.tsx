import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ComponentType } from "react";
import { Route } from "../routes/_app.depositar";
import { Route as RotaTransferir } from "../routes/_app.transferir";

const mocks = vi.hoisted(() => ({
  depositar: vi.fn(),
  transferir: vi.fn(),
  consultarDestino: vi.fn(),
  navegar: vi.fn(),
  invalidar: vi.fn(),
  conta: { carteira_id: 1 },
}));
vi.mock("@/lib/api", () => ({
  depositar: mocks.depositar,
  transferir: mocks.transferir,
  consultarDestino: mocks.consultarDestino,
  pagarCobranca: vi.fn(),
  consultarCobranca: vi.fn(),
  temTotp: vi.fn(),
  pedeTotp: (valor: number) => valor > 5000,
  LIMITE_AUTENTICACAO_ADICIONAL: 5000,
  ApiError: class extends Error {},
}));
vi.mock("@/components/payflow/liveness", () => ({ LivenessCheck: () => null }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ conta: mocks.conta }) }));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidar }),
  useQuery: () => ({ data: undefined, refetch: vi.fn() }),
}));
vi.mock("@tanstack/react-router", async (original) => ({
  ...(await original<typeof import("@tanstack/react-router")>()),
  useNavigate: () => mocks.navegar,
}));
const Depositar = Route.options.component as ComponentType;
beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  mocks.conta = { carteira_id: 1 };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("bloqueia reenvio simultâneo e mantém a chave após falha de rede", async () => {
  let recusar!: (erro: Error) => void;
  mocks.depositar.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        recusar = reject;
      }),
  );
  const { container } = render(<Depositar />);
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1000" } });
  const form = container.querySelector("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(mocks.depositar).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Valor (R$)")).toBeDisabled();
  const primeira: unknown = mocks.depositar.mock.calls[0]?.[0];
  await act(async () => {
    recusar(new Error("Rede caiu"));
  });
  expect(screen.getByText("Rede caiu")).toBeInTheDocument();
  mocks.depositar.mockResolvedValueOnce({ id: 1 });
  await act(async () => {
    fireEvent.submit(form);
  });
  expect(mocks.depositar.mock.calls[1]?.[0]).toEqual(primeira);
  expect(screen.getByText("Depósito confirmado")).toBeInTheDocument();
});

it("trocar de conta limpa valor e erro da conta anterior", async () => {
  mocks.depositar.mockRejectedValueOnce(new Error("Erro da primeira conta"));
  const tela = render(<Depositar />);
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1000" } });
  await act(async () => {
    fireEvent.submit(tela.container.querySelector("form")!);
  });
  expect(screen.getByText("Erro da primeira conta")).toBeInTheDocument();
  mocks.conta = { carteira_id: 2 };
  tela.rerender(<Depositar />);
  expect(screen.getByLabelText("Valor (R$)")).toHaveValue("");
  expect(screen.queryByText("Erro da primeira conta")).not.toBeInTheDocument();
});

it("trocar de conta cancela o redirecionamento do depósito anterior", async () => {
  mocks.depositar.mockResolvedValueOnce({ id: 1 });
  const tela = render(<Depositar />);
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1000" } });
  await act(async () => {
    fireEvent.submit(tela.container.querySelector("form")!);
  });
  mocks.conta = { carteira_id: 2 };
  tela.rerender(<Depositar />);
  await act(async () => {
    vi.advanceTimersByTime(1200);
  });
  expect(mocks.navegar).not.toHaveBeenCalled();
});

it("Pix bloqueia clique repetido e conserva a intenção após erro de rede", async () => {
  const Transferir = RotaTransferir.options.component as ComponentType;
  mocks.consultarDestino.mockResolvedValueOnce({
    nome: "Pessoa fictícia",
    tipo: "PF",
    destino: { numero: "12345678-9" },
  });
  let recusar!: (erro: Error) => void;
  mocks.transferir.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        recusar = reject;
      }),
  );
  const tela = render(<Transferir />);
  fireEvent.change(screen.getByLabelText("Chave Pix ou conta"), {
    target: { value: "12345678-9" },
  });
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "10,00" } });
  await act(async () => {
    fireEvent.submit(tela.container.querySelector("form")!);
  });
  fireEvent.click(screen.getByText("Confirmar transferência"));
  fireEvent.change(screen.getByLabelText("Senha da conta"), { target: { value: "s3nh@" } });
  const confirmar = screen.getByRole("button", { name: "Confirmar" });
  fireEvent.click(confirmar);
  fireEvent.click(confirmar);
  expect(mocks.transferir).toHaveBeenCalledTimes(1);
  const primeira: unknown = mocks.transferir.mock.calls[0]?.[0];
  await act(async () => {
    recusar(new Error("Rede caiu"));
  });
  expect(screen.getByText("Rede caiu")).toBeInTheDocument();
  mocks.transferir.mockResolvedValueOnce({ tipo: "transacao", transacao: { id: 123 } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
  });
  expect(mocks.transferir.mock.calls[1]?.[0]).toEqual(primeira);
  expect(mocks.navegar).toHaveBeenCalledWith({ to: "/comprovante/$id", params: { id: "123" } });
});

it("resposta atrasada de depósito não redireciona a nova conta", async () => {
  let concluir!: (valor: unknown) => void;
  mocks.depositar.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        concluir = resolve;
      }),
  );
  const tela = render(<Depositar />);
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1000" } });
  fireEvent.submit(tela.container.querySelector("form")!);
  mocks.conta = { carteira_id: 2 };
  tela.rerender(<Depositar />);
  await act(async () => {
    concluir({ id: 1 });
  });
  await act(async () => {
    vi.advanceTimersByTime(1200);
  });
  expect(mocks.navegar).not.toHaveBeenCalled();
  expect(screen.queryByText("Depósito confirmado")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Valor (R$)")).toHaveValue("");
});
