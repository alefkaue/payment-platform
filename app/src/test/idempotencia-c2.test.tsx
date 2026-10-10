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
  fireEvent.click(screen.getByText("Confirmar transferência"));
  await screen.findByText("Rede caiu");
  const primeira = vi.mocked(transferir).mock.calls[0]![0].idempotency_key;
  fireEvent.click(screen.getByText("Confirmar transferência"));
  await waitFor(() => expect(transferir).toHaveBeenCalledTimes(2));
  expect(vi.mocked(transferir).mock.calls[1]![0].idempotency_key).toBe(primeira);
  await waitFor(() =>
    expect(screen.getByText("Confirmar transferência").hasAttribute("disabled")).toBe(false),
  );
  fireEvent.click(screen.getByText("Voltar"));
  await revisar("20");
  fireEvent.click(screen.getByText("Confirmar transferência"));
  await waitFor(() => expect(transferir).toHaveBeenCalledTimes(3));
  const segunda = vi.mocked(transferir).mock.calls[2]![0].idempotency_key;
  expect(segunda).not.toBe(primeira);
  await waitFor(() =>
    expect(screen.getByText("Confirmar transferência").hasAttribute("disabled")).toBe(false),
  );
  fireEvent.click(screen.getByText("Voltar"));
  await revisar("20", "456");
  vi.mocked(transferir).mockResolvedValue(sucesso as Awaited<ReturnType<typeof transferir>>);
  fireEvent.click(screen.getByText("Confirmar transferência"));
  await screen.findByText("Revisar");
  const terceira = vi.mocked(transferir).mock.calls[3]![0].idempotency_key;
  expect(terceira).not.toBe(segunda);
  await revisar("20", "456");
  fireEvent.click(screen.getByText("Confirmar transferência"));
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
  fireEvent.click(await screen.findByText("Confirmar pagamento"));
  await screen.findByText("Rede caiu");
  fireEvent.click(screen.getByText("Confirmar pagamento"));
  await waitFor(() => expect(pagarCobranca).toHaveBeenCalledTimes(2));
  expect(vi.mocked(pagarCobranca).mock.calls[0]![1]).toBe(
    vi.mocked(pagarCobranca).mock.calls[1]![1],
  );
});
it("folha mantém chave após falha e muda com valor e nova operação", async () => {
  vi.mocked(pagarFolha).mockRejectedValue(new Error("Rede caiu"));
  abrir(Folha);
  fireEvent.click(await screen.findByRole("button", { name: /Ana.*100/ }));
  fireEvent.click(screen.getByRole("button", { name: "Pagar folha" }));
  await screen.findByText("Rede caiu");
  fireEvent.click(screen.getByRole("button", { name: "Pagar folha" }));
  await waitFor(() => expect(pagarFolha).toHaveBeenCalledTimes(2));
  const primeira = vi.mocked(pagarFolha).mock.calls[0]![3];
  expect(vi.mocked(pagarFolha).mock.calls[1]![3]).toBe(primeira);
  await waitFor(() =>
    expect(screen.getByLabelText("Valor para Ana (R$)").hasAttribute("disabled")).toBe(false),
  );
  fireEvent.change(screen.getByLabelText("Valor para Ana (R$)"), { target: { value: "120" } });
  vi.mocked(pagarFolha).mockResolvedValue({
    resultados: [{ funcionario_id: 2, situacao: "pago", transacao_id: 1 }],
  });
  fireEvent.click(screen.getByRole("button", { name: "Pagar folha" }));
  await waitFor(() => expect(screen.queryByLabelText("Valor para Ana (R$)")).toBeNull());
  const segunda = vi.mocked(pagarFolha).mock.calls[2]![3];
  expect(segunda).not.toBe(primeira);
  fireEvent.click(screen.getByRole("button", { name: /Ana.*100/ }));
  fireEvent.change(screen.getByLabelText("Valor para Ana (R$)"), { target: { value: "120" } });
  fireEvent.click(screen.getByRole("button", { name: "Pagar folha" }));
  await waitFor(() => expect(pagarFolha).toHaveBeenCalledTimes(4));
  expect(vi.mocked(pagarFolha).mock.calls[3]![3]).not.toBe(segunda);
});
