import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  AmbienteAndroid,
  atualizarConexao,
  BotaoFinanceiro,
  criarVoltar,
  PilhaVoltar,
} from "@/lib/mobile";
import { Route as Transferir } from "@/routes/_app.transferir";
import { Route as Depositar } from "@/routes/_app.depositar";
import { Route as Folha } from "@/routes/_app.folha";
import { App } from "@capacitor/app";
import { Network } from "@capacitor/network";
import { Capacitor } from "@capacitor/core";
import { consultarDestino, transferir } from "@/lib/api";
import { CampoDocumento } from "@/components/payflow/documento";

vi.mock("@capacitor/core", async (original) => ({
  ...(await original<typeof import("@capacitor/core")>()),
  Capacitor: { isNativePlatform: vi.fn(() => false) },
}));
vi.mock("@capacitor/app", () => ({
  App: { addListener: vi.fn(async () => ({ remove: vi.fn() })), exitApp: vi.fn() },
}));
vi.mock("@capacitor/network", () => ({
  Network: {
    addListener: vi.fn(async () => ({ remove: vi.fn() })),
    getStatus: vi.fn(async () => ({ connected: true })),
  },
}));
vi.mock("@capacitor/status-bar", () => ({
  Style: { Dark: "DARK" },
  StatusBar: { setBackgroundColor: vi.fn(async () => {}), setStyle: vi.fn(async () => {}) },
}));
vi.mock("@capacitor/keyboard", () => ({
  Keyboard: { addListener: vi.fn(async () => ({ remove: vi.fn() })) },
}));
const router = vi.hoisted(() => ({
  state: { location: { pathname: "/inicio" } },
  history: { canGoBack: () => true, back: vi.fn() },
  navigate: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({
  useRouter: () => router,
  useNavigate: () => vi.fn(),
  createFileRoute: () => (options: unknown) => ({ options }),
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ conta: { carteira_id: 1, numero: "1", tipo: "PJ", papel: "admin" } }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  consultarDestino: vi.fn(async () => ({
    carteira_id: 2,
    nome: "Destino",
    tipo: "PF",
    destino: { numero: "2" },
  })),
  transferir: vi.fn(),
  funcionarios: vi.fn(async () => [
    { id: 2, nome: "Ana", cpf: "***", salario: "100.00", ativo: true },
  ]),
}));
beforeEach(() => {
  vi.clearAllMocks();
  atualizarConexao(true);
  vi.mocked(Capacitor.isNativePlatform).mockReturnValue(false);
});
afterEach(() => {
  cleanup();
  atualizarConexao(true);
});
function abrir(rota: typeof Transferir | typeof Depositar | typeof Folha) {
  const Tela = rota.options.component!;
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Tela />
    </QueryClientProvider>,
  );
}

it("Voltar fecha Mais, câmera e confirmação antes de navegar", () => {
  const pilha = new PilhaVoltar();
  const ordem: string[] = [];
  pilha.registrar(() => ordem.push("confirmação"));
  pilha.registrar(() => ordem.push("câmera"), 50);
  const remover = pilha.registrar(() => ordem.push("desmontado"), 60);
  remover();
  pilha.registrar(() => ordem.push("Mais"), 30);
  const voltar = criarVoltar({
    fechar: () => pilha.fechar(),
    inicio: () => false,
    voltar: () => ordem.push("rota"),
    avisar: vi.fn(),
    sair: vi.fn(),
  });
  voltar();
  voltar();
  voltar();
  voltar();
  expect(ordem).toEqual(["câmera", "Mais", "confirmação", "rota"]);
});
it("fecha a última confirmação e exige dois toques próximos para sair", () => {
  const pilha = new PilhaVoltar();
  const primeiro = vi.fn();
  const ultimo = vi.fn();
  pilha.registrar(primeiro);
  pilha.registrar(ultimo);
  pilha.fechar();
  expect(ultimo).toHaveBeenCalledOnce();
  expect(primeiro).not.toHaveBeenCalled();
  let tempo = 0;
  const avisar = vi.fn();
  const sair = vi.fn();
  const voltar = criarVoltar({
    fechar: () => false,
    inicio: () => true,
    voltar: vi.fn(),
    avisar,
    sair,
    agora: () => tempo,
  });
  voltar();
  tempo = 3000;
  voltar();
  expect(sair).not.toHaveBeenCalled();
  tempo = 4000;
  voltar();
  expect(sair).toHaveBeenCalledOnce();
  expect(avisar).toHaveBeenCalledTimes(2);
});
it("não registra plugins no navegador", () => {
  render(<AmbienteAndroid />);
  expect(App.addListener).not.toHaveBeenCalled();
  expect(Network.getStatus).not.toHaveBeenCalled();
});
it("documento prefere a câmera traseira", () => {
  const { container } = render(
    <CampoDocumento rotulo="Documento" valor={null} onChange={vi.fn()} />,
  );
  expect(container.querySelector('input[type="file"]')).toHaveAttribute("capture", "environment");
});
it("detector nativo exibe offline e bloqueia ações mantendo bloqueios anteriores", async () => {
  vi.mocked(Capacitor.isNativePlatform).mockReturnValue(true);
  render(
    <>
      <AmbienteAndroid />
      <BotaoFinanceiro>Confirmar</BotaoFinanceiro>
      <BotaoFinanceiro disabled>Ocupado</BotaoFinanceiro>
    </>,
  );
  await waitFor(() => expect(Network.addListener).toHaveBeenCalled());
  const listener = vi.mocked(Network.addListener).mock.calls[0]![1];
  act(() => listener({ connected: false, connectionType: "none" }));
  expect(screen.getByText("Sem conexão")).toBeVisible();
  expect(screen.getByText("Confirmar")).toBeDisabled();
  act(() => listener({ connected: true, connectionType: "wifi" }));
  expect(screen.getByText("Confirmar")).toBeEnabled();
  expect(screen.getByText("Ocupado")).toBeDisabled();
});
it("a confirmação real de Pix fica desabilitada se a rede cai depois da revisão", async () => {
  abrir(Transferir);
  fireEvent.change(screen.getByLabelText("Chave Pix ou conta"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "10" } });
  fireEvent.click(screen.getByText("Revisar"));
  const confirmar = await screen.findByText("Confirmar transferência");
  expect(consultarDestino).toHaveBeenCalled();
  act(() => atualizarConexao(false));
  expect(confirmar).toBeDisabled();
  fireEvent.click(confirmar);
  expect(transferir).not.toHaveBeenCalled();
});
it.each([Transferir, Depositar])("campo de valor usa teclado decimal", (rota) => {
  abrir(rota);
  expect(screen.getByLabelText("Valor (R$)")).toHaveAttribute("inputmode", "decimal");
});
it("salário da folha e valor por funcionário usam teclado decimal", async () => {
  abrir(Folha);
  await screen.findByText("Ana");
  fireEvent.click(screen.getByText("Ana"));
  expect(screen.getByLabelText("Valor para Ana (R$)")).toHaveAttribute("inputmode", "decimal");
  fireEvent.click(screen.getByText("Cadastrar funcionário"));
  expect(screen.getByLabelText("Salário (R$, opcional)")).toHaveAttribute("inputmode", "decimal");
});
