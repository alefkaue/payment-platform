import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route as Contas } from "@/routes/_app.contas";
import { Route as Inicio, SaldoBloqueado } from "@/routes/_app.inicio";
import { TxItem } from "@/components/payflow/ui";
import { listarFaturas, minhaConta, transacoes } from "@/lib/api";
import type { Conta, Fatura, Transacao } from "@/lib/types";

const estado = vi.hoisted(() => ({
  api: false,
  conta: {
    tipo: "PJ",
    papel: "admin",
    numero: "3050",
    carteira_id: 3050,
    saldo: 50,
    saldo_bloqueado: 100,
  } as Conta,
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ conta: estado.conta }) }));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  Navigate: () => null,
  Link: ({
    children,
    to,
    className,
  }: {
    children: React.ReactNode;
    to: string;
    className?: string;
  }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  get MODO_API() {
    return estado.api;
  },
  listarFaturas: vi.fn(),
  minhaConta: vi.fn(),
  transacoes: vi.fn(),
}));
const tx: Transacao = {
  id: 1,
  origem_carteira_id: 1042,
  destino_carteira_id: 3050,
  valor_bruto: 100,
  liquido: 100,
  cbs: 0,
  ibs: 0,
  aplicou_split: false,
  tipo_destino: "PJ",
  auth_metodo: "senha",
  status: "retida",
  bloqueio_ate: "2026-10-13T10:00:00Z",
  criado_em: "2026-10-10T10:00:00Z",
  categoria: "transferencia",
  descricao: "Entrada retida",
};
const fatura: Fatura = {
  id: 1,
  direcao: "receber",
  contraparte: "Aberta",
  nf: "Sem nota",
  valor_bruto: 10,
  liquido: 10,
  imposto: 0,
  credito_gerado: 0,
  vencimento: "2026-10-20",
  status: "pendente",
};
function abrir(elemento: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{elemento}</QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  estado.api = false;
  estado.conta.tipo = "PJ";
  vi.mocked(minhaConta).mockResolvedValue({ ...estado.conta });
  vi.mocked(transacoes).mockResolvedValue([{ ...tx }]);
  vi.mocked(listarFaturas).mockResolvedValue([
    fatura,
    { ...fatura, id: 2, contraparte: "Paga", liquido: 500, status: "liquidado" },
  ]);
});
afterEach(cleanup);
it.each([false, true])("separa abertas do histórico e soma só abertas (API=%s)", async (api) => {
  estado.api = api;
  const Component = Contas.options.component!;
  abrir(<Component />);
  await screen.findByText("Aberta");
  expect(screen.queryByText("Paga")).toBeNull();
  expect(screen.getAllByText(/10,00/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/510,00/)).toBeNull();
  expect(screen.getByText(/vence/)).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "Recebidas" }));
  expect(screen.getByText("Paga")).toBeTruthy();
  expect(screen.queryByText("Aberta")).toBeNull();
  expect(screen.queryByText(/vence/)).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "A pagar" }));
  expect(screen.getByText("Ainda não há contas a pagar")).toBeTruthy();
  if (api) {
    expect(screen.getByText("Ainda indisponível")).toBeTruthy();
    expect(
      screen.getByText("O cadastro de contas a pagar ainda não está disponível."),
    ).toBeTruthy();
  }
});
it.each(["PF", "PJ"] as const)(
  "Início %s mostra saldo disponível separado e link do bloqueado",
  async (tipo) => {
    estado.conta.tipo = tipo;
    vi.mocked(minhaConta).mockResolvedValue({ ...estado.conta });
    const Component = Inicio.options.component!;
    abrir(<Component />);
    const aviso = await screen.findByText(/100,00.*bloqueado por segurança/);
    expect(aviso.getAttribute("href")).toBe("/extrato");
    expect(screen.getByText("Saldo disponível")).toBeTruthy();
    expect(screen.getByText(/50,00/)).toBeTruthy();
    expect(screen.queryByText(/150,00/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ocultar saldo" }));
    expect(screen.queryByText(/100,00.*bloqueado por segurança/)).toBeNull();
  },
);
it("mostra prazo conhecido, oculta zero e não inventa data quando ausente", async () => {
  const view = abrir(<SaldoBloqueado valor={100} minha={3050} visivel />);
  expect(await screen.findByText(/libera até/)).toBeTruthy();
  view.unmount();
  const zero = abrir(<SaldoBloqueado valor={0} minha={3050} visivel />);
  expect(screen.queryByText(/bloqueado por segurança/)).toBeNull();
  zero.unmount();
  vi.mocked(transacoes).mockResolvedValue([{ ...tx, bloqueio_ate: "" }]);
  abrir(<SaldoBloqueado valor={100} minha={3050} visivel />);
  expect(screen.queryByText(/libera até/)).toBeNull();
});
it("extrato mostra selo e liberação apenas na entrada retida", () => {
  const view = abrir(
    <ul>
      <TxItem t={tx} minha={3050} clicavel={false} />
    </ul>,
  );
  expect(screen.getByText("retido")).toBeTruthy();
  expect(screen.getByText(/libera até/)).toBeTruthy();
  view.unmount();
  abrir(
    <ul>
      <TxItem t={tx} minha={1042} clicavel={false} />
    </ul>,
  );
  expect(screen.queryByText("retido")).toBeNull();
});
