import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApuracaoCard, CreditosCard } from "@/routes/_app.inicio";
import { Route as Contas } from "@/routes/_app.contas";
import { Route as Comprovante } from "@/routes/_app.comprovante.$id";
import { TxItem } from "@/components/payflow/ui";
import {
  apuracaoPJ,
  criarCobranca,
  listarCobrancas,
  listarFaturas,
  transacaoPorId,
} from "@/lib/api";
import { TEXTO_INFORMATIVO, TEXTO_DEMONSTRACAO } from "@/lib/split-fase";
import type { ApuracaoPJ, SplitFase, Transacao } from "@/lib/types";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ conta: { tipo: "PJ", papel: "admin", numero: "3050", carteira_id: 3050 } }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options, useParams: () => ({ id: "1" }) }),
  Navigate: () => null,
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  apuracaoPJ: vi.fn(),
  listarFaturas: vi.fn(),
  listarCobrancas: vi.fn(),
  criarCobranca: vi.fn(),
  transacaoPorId: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function abrir(elemento: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{elemento}</QueryClientProvider>);
}
function resumo(fase: SplitFase): ApuracaoPJ {
  return {
    split_fase: fase,
    imposto_destacado: 123,
    imposto_retido: fase === "informativo" ? 0 : 100,
    cbs_retido: 90,
    ibs_retido: 10,
    a_repassar: 10,
    repassado: 90,
    creditos_informados: 0,
    restituicao_prevista: 0,
    vendas_com_split: 1,
    faturamento: 1000,
    periodo: "Outubro de 2026",
    observacao: "Observação do servidor",
    split_retencao_desde: "2027-01-01",
  };
}
const tx: Transacao = {
  id: 1,
  origem_carteira_id: 1042,
  destino_carteira_id: 3050,
  valor_bruto: 1000,
  liquido: 900,
  cbs: 90,
  ibs: 10,
  aplicou_split: false,
  tipo_destino: "PJ",
  auth_metodo: "senha",
  categoria: "compra",
  descricao: "Compra com nota",
  criado_em: "2026-10-10T10:00:00Z",
};

it.each(["informativo", "retencao", "demonstracao"] as const)(
  "Início PJ comunica a fase %s",
  async (fase) => {
    vi.mocked(apuracaoPJ).mockResolvedValue(resumo(fase));
    const view = abrir(
      <>
        <ApuracaoCard />
        <CreditosCard creditos={0} />
      </>,
    );
    await screen.findByText(
      fase === "informativo" ? TEXTO_INFORMATIVO : "Retido das notas e separado para o Fisco",
    );
    if (fase === "informativo") {
      expect(screen.getAllByText(/123,00/)).toHaveLength(2);
      expect(screen.getByText("não saiu do seu caixa em 2026")).toBeTruthy();
      expect(view.container.textContent).not.toMatch(
        /Fisco|Retido das notas|retido no ato|Repasse amanhã|Já repassado/,
      );
    } else {
      expect(screen.getByText("Imposto separado no recebimento")).toBeTruthy();
      expect(screen.getAllByText(/100,00/)).toHaveLength(2);
      expect(screen.getByText(/Repasse amanhã/)).toBeTruthy();
    }
    expect(screen.queryByText("Caixa preservado no mês")).toBeNull();
    expect(screen.queryByText("Simulação") !== null).toBe(fase === "demonstracao");
    if (fase === "demonstracao") expect(screen.getByText(TEXTO_DEMONSTRACAO)).toBeTruthy();
  },
);

it.each(["informativo", "retencao", "demonstracao"] as const)(
  "Contas e criação comunicam a fase %s",
  async (fase) => {
    vi.mocked(apuracaoPJ).mockResolvedValue(resumo(fase));
    vi.mocked(listarFaturas).mockResolvedValue([]);
    vi.mocked(criarCobranca).mockResolvedValue([
      {
        id: 1,
        txid: "teste",
        valor: 1000,
        cbs: 90,
        ibs: 10,
        split_fase: fase,
        vai_reter_imposto: fase !== "informativo",
        pix_copia_e_cola: "TESTE",
        linha_digitavel: "",
        status: "aberta",
        parcela_numero: 1,
        parcelas_total: 1,
      },
    ]);
    const Component = Contas.options.component!;
    const view = abrir(<Component />);
    await screen.findByText(
      fase === "informativo" ? TEXTO_INFORMATIVO : "Imposto separado para o Fisco",
    );
    if (fase === "informativo")
      expect(view.container.textContent).not.toMatch(/Fisco|retido no ato|imposto retido/);
    expect(screen.queryByText("Simulação") !== null).toBe(fase === "demonstracao");
    fireEvent.click(screen.getByRole("button", { name: "Cobrar um cliente" }));
    fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Chave de acesso da NF-e"), {
      target: { value: "1".repeat(44) },
    });
    fireEvent.change(screen.getByLabelText("CBS da nota (R$)"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("IBS da nota (R$)"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Criar cobrança" }));
    await screen.findByText("Cobrança criada");
    if (fase === "informativo") {
      expect(
        screen.getByText(/Imposto destacado na nota:.*100,00.*não retido em 2026.*1.000,00/),
      ).toBeTruthy();
      expect(view.container.textContent).not.toContain("Fisco");
    } else expect(screen.getByText(/são separados para o Fisco/)).toBeTruthy();
  },
);

it("TxItem PF com nota sem split não anuncia retenção e PJ recebe inteiro", () => {
  const view = abrir(
    <ul>
      <TxItem t={tx} minha={1042} clicavel={false} />
      <TxItem t={tx} minha={3050} clicavel={false} />
    </ul>,
  );
  expect(view.container.textContent).not.toMatch(/Fisco|retido|Imposto da nota|900,00/);
  expect(screen.getAllByText(/1.000,00/)).toHaveLength(2);
});

it("comprovante sem split destaca imposto sem descontar do destino", async () => {
  vi.mocked(apuracaoPJ).mockResolvedValue(resumo("informativo"));
  vi.mocked(transacaoPorId).mockResolvedValue(tx);
  const Component = Comprovante.options.component!;
  abrir(<Component />);
  expect(
    await screen.findByText(/Imposto destacado na nota:.*100,00.*não retido em 2026/),
  ).toBeTruthy();
  expect(screen.queryByText(/Fisco|900,00/)).toBeNull();
  expect(screen.getAllByText(/1.000,00/)).toHaveLength(3);
});

it("comprovante PJ recupera destaque da cobrança quando a API zera tributos da transação", async () => {
  vi.mocked(apuracaoPJ).mockResolvedValue(resumo("informativo"));
  vi.mocked(transacaoPorId).mockResolvedValue({
    ...tx,
    categoria: "recebimento",
    cbs: 0,
    ibs: 0,
    liquido: 1000,
  });
  vi.mocked(listarCobrancas).mockResolvedValue([
    {
      id: 1,
      txid: "teste",
      transacao_id: 1,
      valor: 1000,
      cbs: 90,
      ibs: 10,
      split_fase: "informativo",
      vai_reter_imposto: false,
      status: "paga",
      pix_copia_e_cola: "",
      linha_digitavel: "",
      parcela_numero: 1,
      parcelas_total: 1,
    },
  ]);
  const Component = Comprovante.options.component!;
  abrir(<Component />);
  expect(
    await screen.findByText(/Imposto destacado na nota:.*100,00.*não retido em 2026/),
  ).toBeTruthy();
  expect(screen.queryByText(/Fisco/)).toBeNull();
});
