import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route as Transferir } from "@/routes/_app.transferir";
import { Route as Folha } from "@/routes/_app.folha";
import {
  consultarDestino,
  consultarCobranca,
  transferir,
  pagarCobranca,
  funcionarios,
  pagarFolha,
} from "@/lib/api";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ conta: { carteira_id: 1, tipo: "PJ", papel: "admin" } }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  consultarDestino: vi.fn(),
  consultarCobranca: vi.fn(),
  transferir: vi.fn(),
  pagarCobranca: vi.fn(),
  funcionarios: vi.fn(),
  pagarFolha: vi.fn(),
}));
const sucesso = { tipo: "transacao" as const, transacao: { id: 1 } };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(consultarDestino).mockImplementation(async (numero) => ({
    carteira_id: 2,
    nome: "Destino",
    tipo: "PF",
    destino: { numero },
  }));
  vi.mocked(funcionarios).mockResolvedValue([
    { id: 2, nome: "Ana", cpf: "***", salario: "100.00", cargo: null, ativo: true },
  ]);
});
afterEach(cleanup);
function abrir(rota: typeof Transferir | typeof Folha) {
  const Component = rota.options.component!;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Component />
    </QueryClientProvider>,
  );
}
/** Abre a confirmação (senha) e confirma; com a janela já aberta, só confirma de novo. */
function confirmar(botao: string, acao = "Confirmar") {
  if (!screen.queryByRole("dialog")) {
    fireEvent.click(screen.getByRole("button", { name: botao }));
    fireEvent.change(screen.getByLabelText("Senha da conta"), { target: { value: "s3nh@" } });
  }
  fireEvent.click(screen.getByRole("button", { name: acao }));
}
const fecharConfirmacao = () =>
  fireEvent.click(screen.getAllByRole("button", { name: "Fechar" })[1]!);
async function revisar(valor = "10", destino = "123") {
  fireEvent.change(screen.getByLabelText("Chave Pix ou conta"), { target: { value: destino } });
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: valor } });
  fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
  await screen.findByRole("button", { name: "Confirmar transferência" });
}
it("Pix preserva chave após erro, troca com valor/destino e renova depois do sucesso", async () => {
  vi.mocked(transferir).mockRejectedValue(new Error("Rede caiu"));
  abrir(Transferir);
  await revisar();
  confirmar("Confirmar transferência");
  await screen.findByText("Rede caiu");
  const primeira = vi.mocked(transferir).mock.calls[0]![0].idempotency_key;
  expect(vi.mocked(transferir).mock.calls[0]![0].confirmacao).toEqual({ senha: "s3nh@" });
  confirmar("Confirmar transferência");
  await waitFor(() => expect(transferir).toHaveBeenCalledTimes(2));
  expect(vi.mocked(transferir).mock.calls[1]![0].idempotency_key).toBe(primeira);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Confirmar" }).hasAttribute("disabled")).toBe(false),
  );
  fecharConfirmacao();
  fireEvent.click(screen.getByText("Voltar"));
  await revisar("20");
  confirmar("Confirmar transferência");
  await waitFor(() => expect(transferir).toHaveBeenCalledTimes(3));
  const segunda = vi.mocked(transferir).mock.calls[2]![0].idempotency_key;
  expect(segunda).not.toBe(primeira);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Confirmar" }).hasAttribute("disabled")).toBe(false),
  );
  fecharConfirmacao();
  fireEvent.click(screen.getByText("Voltar"));
  await revisar("20", "456");
  vi.mocked(transferir).mockResolvedValue(sucesso as Awaited<ReturnType<typeof transferir>>);
  confirmar("Confirmar transferência");
  await screen.findByText("Revisar");
  expect(screen.queryByRole("dialog")).toBeNull();
  const terceira = vi.mocked(transferir).mock.calls[3]![0].idempotency_key;
  expect(terceira).not.toBe(segunda);
  await revisar("20", "456");
  confirmar("Confirmar transferência");
  await waitFor(() => expect(transferir).toHaveBeenCalledTimes(5));
  expect(vi.mocked(transferir).mock.calls[4]![0].idempotency_key).not.toBe(terceira);
});
it("cobrança mantém chave em tentativa após falha de rede", async () => {
  vi.mocked(consultarCobranca).mockResolvedValue({
    id: 1,
    txid: "c2-txid",
    valor: 10,
    status: "aberta",
    cbs: 0,
    ibs: 0,
    pix_copia_e_cola: "",
    linha_digitavel: "",
    parcela_numero: 1,
    parcelas_total: 1,
    vai_reter_imposto: false,
  });
  vi.mocked(pagarCobranca).mockRejectedValue(new Error("Rede caiu"));
  abrir(Transferir);
  fireEvent.click(screen.getByLabelText("Pagar cobrança pelo identificador (txid)"));
  fireEvent.change(screen.getByLabelText("Identificador da cobrança (txid)"), {
    target: { value: "c2-txid" },
  });
  fireEvent.click(screen.getByText("Revisar"));
  await screen.findByRole("button", { name: "Confirmar pagamento" });
  confirmar("Confirmar pagamento");
  await screen.findByText("Rede caiu");
  confirmar("Confirmar pagamento");
  await waitFor(() => expect(pagarCobranca).toHaveBeenCalledTimes(2));
  expect(vi.mocked(pagarCobranca).mock.calls[0]![1]).toBe(
    vi.mocked(pagarCobranca).mock.calls[1]![1],
  );
});
it("folha mantém chave após falha e muda com valor e nova operação", async () => {
  vi.mocked(pagarFolha).mockRejectedValue(new Error("Rede caiu"));
  abrir(Folha);
  fireEvent.click(await screen.findByRole("button", { name: /Ana.*100/ }));
  confirmar("Pagar folha", "Pagar salários");
  await screen.findByText("Rede caiu");
  expect(vi.mocked(pagarFolha).mock.calls[0]![2]).toEqual({ senha: "s3nh@" });
  confirmar("Pagar folha", "Pagar salários");
  await waitFor(() => expect(pagarFolha).toHaveBeenCalledTimes(2));
  const primeira = vi.mocked(pagarFolha).mock.calls[0]![3];
  expect(vi.mocked(pagarFolha).mock.calls[1]![3]).toBe(primeira);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Pagar salários" }).hasAttribute("disabled")).toBe(
      false,
    ),
  );
  fecharConfirmacao();
  fireEvent.change(screen.getByLabelText("Valor para Ana (R$)"), { target: { value: "120" } });
  vi.mocked(pagarFolha).mockResolvedValue({
    resultados: [{ funcionario_id: 2, situacao: "pago", transacao_id: 1 }],
  });
  confirmar("Pagar folha", "Pagar salários");
  await waitFor(() => expect(screen.queryByLabelText("Valor para Ana (R$)")).toBeNull());
  const segunda = vi.mocked(pagarFolha).mock.calls[2]![3];
  expect(segunda).not.toBe(primeira);
  fireEvent.click(screen.getByRole("button", { name: /Ana.*100/ }));
  fireEvent.change(screen.getByLabelText("Valor para Ana (R$)"), { target: { value: "120" } });
  confirmar("Pagar folha", "Pagar salários");
  await waitFor(() => expect(pagarFolha).toHaveBeenCalledTimes(4));
  expect(vi.mocked(pagarFolha).mock.calls[3]![3]).not.toBe(segunda);
});
