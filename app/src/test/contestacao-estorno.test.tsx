import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route as Comprovante } from "@/routes/_app.comprovante.$id";
import { Route as Contas } from "@/routes/_app.contas";
import { contestar, estornarCobranca, listarFaturas, transacaoPorId } from "@/lib/api";
import type { Fatura, Transacao } from "@/lib/types";

const auth = vi.hoisted(() => ({
  conta: { tipo: "PJ", papel: "admin", numero: "3050", carteira_id: 3050 },
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options, useParams: () => ({ id: "7" }) }),
  Navigate: () => null,
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/routes/_app.inicio", () => ({
  FaturaRow: ({ f }: { f: Fatura }) => <li>{f.contraparte}</li>,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  contestar: vi.fn(),
  estornarCobranca: vi.fn(),
  listarFaturas: vi.fn(),
  transacaoPorId: vi.fn(),
}));
const tx: Transacao = {
  id: 7,
  origem_carteira_id: 3050,
  destino_carteira_id: 1042,
  valor_bruto: 150.25,
  liquido: 150.25,
  cbs: 0,
  ibs: 0,
  aplicou_split: false,
  tipo_destino: "PF",
  auth_metodo: "senha",
  status: "concluida",
  categoria: "transferencia",
  descricao: "Pix para Ana",
  criado_em: new Date().toISOString(),
};
const fatura: Fatura = {
  id: 8,
  txid: "pedido-pago",
  direcao: "receber",
  contraparte: "Cliente",
  nf: "Sem nota",
  valor_bruto: 150.25,
  liquido: 148.75,
  imposto: 1.5,
  credito_gerado: 0,
  vencimento: new Date().toISOString(),
  status: "liquidado",
};
beforeEach(() => {
  vi.clearAllMocks();
  auth.conta.papel = "admin";
  vi.mocked(transacaoPorId).mockResolvedValue({ ...tx });
  vi.mocked(listarFaturas).mockResolvedValue([{ ...fatura }]);
  vi.mocked(contestar).mockResolvedValue(undefined);
  vi.mocked(estornarCobranca).mockResolvedValue({ ...tx, categoria: "estorno" });
});
afterEach(cleanup);
function abrir(rota: typeof Comprovante | typeof Contas) {
  const Component = rota.options.component!;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidar = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <Component />
    </QueryClientProvider>,
  );
  return invalidar;
}
it("contesta com motivo mínimo, contador e estado de sucesso", async () => {
  abrir(Comprovante);
  fireEvent.click(await screen.findByRole("button", { name: "Contestar" }));
  const enviar = screen.getByRole("button", { name: "Enviar contestação" });
  expect(enviar.hasAttribute("disabled")).toBe(true);
  fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "Golpe" } });
  expect(screen.getByText("5/280 caracteres")).toBeTruthy();
  fireEvent.click(enviar);
  expect(await screen.findByText("Contestação aberta")).toBeTruthy();
  expect(contestar).toHaveBeenCalledWith(7, "Golpe");
  expect(screen.queryByRole("button", { name: "Contestar" })).toBeNull();
});
it.each([
  { origem_carteira_id: 1042 },
  { status: "retida" },
  { status: "devolvida" },
  { criado_em: new Date(Date.now() - 81 * 86400000).toISOString() },
  { categoria: "deposito" as const },
])("esconde contestação quando não elegível: %j", async (mudanca) => {
  vi.mocked(transacaoPorId).mockResolvedValue({ ...tx, ...mudanca });
  abrir(Comprovante);
  await screen.findByText(/Pix para Ana/);
  expect(screen.queryByRole("button", { name: "Contestar" })).toBeNull();
});
it("mostra erro de contestação na própria tela", async () => {
  vi.mocked(contestar).mockRejectedValueOnce(new Error("Prazo de contestação encerrado."));
  abrir(Comprovante);
  fireEvent.click(await screen.findByRole("button", { name: "Contestar" }));
  fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "Golpe" } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar contestação" }));
  expect(await screen.findByText("Prazo de contestação encerrado.")).toBeTruthy();
});
it("PJ sem admin não vê Contestar", async () => {
  auth.conta.papel = "operador";
  abrir(Comprovante);
  await screen.findByText(/Pix para Ana/);
  expect(screen.queryByRole("button", { name: "Contestar" })).toBeNull();
});
it("estorno espera confirmação do bruto e invalida a lista", async () => {
  const invalidar = abrir(Contas);
  fireEvent.click(await screen.findByRole("button", { name: "Estornar" }));
  expect(estornarCobranca).not.toHaveBeenCalled();
  expect(screen.getByText(/150,25.*voltam ao pagador/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar estorno" }));
  expect(await screen.findByText("Estorno feito")).toBeTruthy();
  expect(estornarCobranca).toHaveBeenCalledWith("pedido-pago", expect.anything());
  await waitFor(() => expect(invalidar).toHaveBeenCalledWith({ queryKey: ["faturas"] }));
});
it.each(["aprovador", "operador", "consulta"])("%s não vê Estornar", async (papel) => {
  auth.conta.papel = papel;
  abrir(Contas);
  await screen.findByText("Cliente");
  expect(screen.queryByRole("button", { name: "Estornar" })).toBeNull();
});
it("cobrança pendente não mostra Estornar", async () => {
  vi.mocked(listarFaturas).mockResolvedValue([{ ...fatura, status: "pendente" }]);
  abrir(Contas);
  await screen.findByText("Cliente");
  expect(screen.queryByRole("button", { name: "Estornar" })).toBeNull();
});
it("cancelar o estorno não envia requisição", async () => {
  abrir(Contas);
  fireEvent.click(await screen.findByRole("button", { name: "Estornar" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(estornarCobranca).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Confirmar estorno" })).toBeNull();
});
it("falha por saldo insuficiente mantém confirmação e não anuncia sucesso", async () => {
  vi.mocked(estornarCobranca).mockRejectedValueOnce(
    new Error("Saldo insuficiente para devolver o valor ao pagador."),
  );
  abrir(Contas);
  fireEvent.click(await screen.findByRole("button", { name: "Estornar" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmar estorno" }));
  expect(
    await screen.findByText("Saldo insuficiente para devolver o valor ao pagador."),
  ).toBeTruthy();
  expect(screen.queryByText("Estorno feito")).toBeNull();
  expect(screen.getByRole("button", { name: "Confirmar estorno" })).toBeTruthy();
});
