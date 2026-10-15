import { beforeEach, expect, it, vi } from "vitest";
import {
  decidirPendente,
  PAGINA_EXTRATO,
  paginaExtrato,
  pendentes,
  podeRepetirFolha,
  repetirPendente,
} from "./api";
import { get, post } from "./http";

// Regressão de REVISAO-PROBLEMAS.md (14/10/2026): R04, R07 e R08 no modo API.
vi.mock("./http", async (original) => ({
  ...(await original<typeof import("./http")>()),
  MODO_API: true,
  get: vi.fn(),
  post: vi.fn(),
}));

const base = {
  valor: "100.00",
  descricao: "Salário 10/2026 — 2 funcionário(s)",
  criado_por_nome: "Op",
  criado_em: "2026-10-14T12:00:00Z",
  aprovacoes_necessarias: 1,
  aprovacoes: [{ usuario_id: 1, nome: "Dona" }],
};

const folhaParcial = {
  ...base,
  id: 7,
  tipo: "folha",
  status: "aprovada",
  payload: {
    itens: [
      { funcionario_id: 1, nome: "Ana" },
      { funcionario_id: 2, nome: "Bia" },
    ],
  },
  resultado: {
    executados: 1,
    itens: 2,
    parcial: true,
    resultados: [
      { funcionario_id: 1, situacao: "pago", transacao_id: 9 },
      { funcionario_id: 2, situacao: "erro", erro: "Saldo insuficiente." },
    ],
  },
};

beforeEach(() => {
  vi.mocked(get).mockReset();
  vi.mocked(post).mockReset();
});

it("R04: folha aprovada sem salário pago mostra a falha e os itens", async () => {
  vi.mocked(post).mockResolvedValue({
    ...folhaParcial,
    status: "falhou",
    resultado: {
      executados: 0,
      itens: 1,
      parcial: false,
      resultados: [{ funcionario_id: 1, situacao: "erro", erro: "Saldo insuficiente." }],
    },
  });
  const r = await decidirPendente(7, true);
  expect(r.status).toBe("falhou");
  expect(r.execucao).toMatchObject({ executados: 0, itens: 1 });
  expect(r.execucao?.resultados[0]).toMatchObject({ nome: "Ana", situacao: "erro" });
  expect(podeRepetirFolha(r)).toBe(true);
});

it("R04: execução parcial preserva quem recebeu e permite repetir só o que falta", async () => {
  vi.mocked(get).mockResolvedValue([folhaParcial]);
  const [o] = await pendentes();
  expect(o!.status).toBe("aprovada");
  expect(o!.execucao).toMatchObject({ executados: 1, itens: 2, parcial: true });
  expect(o!.execucao!.resultados.map((i) => [i.nome, i.situacao])).toEqual([
    ["Ana", "pago"],
    ["Bia", "erro"],
  ]);
  vi.mocked(post).mockResolvedValue({
    ...folhaParcial,
    resultado: { ...folhaParcial.resultado, executados: 2, parcial: false, resultados: [] },
  });
  await repetirPendente(7);
  expect(post).toHaveBeenCalledWith("/pagamentos/pendentes/7/repetir", {});
});

it("R07: carrega todos os estados numa consulta e não chama falha de recusa", async () => {
  const estados = ["pendente", "executando", "rejeitada", "cancelada", "expirada", "falhou"];
  vi.mocked(get).mockResolvedValue(
    estados.map((status, i) => ({
      ...base,
      id: i + 1,
      tipo: "transferencia",
      status,
      criado_em: `2026-10-1${i}T12:00:00Z`,
      resultado: status === "falhou" ? { erro: "Saldo insuficiente." } : null,
    })),
  );
  const lista = await pendentes();
  expect(get).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledWith("/empresas/atual/pendentes?status=");
  expect(lista.map((o) => o.status).sort()).toEqual(
    ["aguardando", "cancelada", "executando", "expirada", "falhou", "recusada"].sort(),
  );
  expect(lista.find((o) => o.status === "falhou")?.erro).toBe("Saldo insuficiente.");
});

it("R08: extrato pede páginas com offset e sabe quando há mais", async () => {
  const tx = (id: number) => ({
    id,
    tipo: "transferencia",
    origem: { carteira_id: 1, agencia: "0001", numero: "1", nome: "Eu" },
    destino: { carteira_id: 2, agencia: "0001", numero: "2", nome: "Outra" },
    valor_bruto: "1.00",
    cbs: "0.00",
    ibs: "0.00",
    liquido: "1.00",
    imposto_total: "0.00",
    tipo_destino: "PF",
    aplicou_split: false,
    auth_metodo: "senha",
    status: "concluida",
    descricao: `Pix ${id}`,
    data_hora: "2026-10-14T12:00:00Z",
  });
  vi.mocked(get).mockImplementation(async (url: string) => {
    if (url === "/contas/atual") return { carteira_id: 1 };
    const offset = Number(new URL(url, "http://x").searchParams.get("offset"));
    const total = 150;
    const fim = Math.min(total, offset + PAGINA_EXTRATO + 1);
    return Array.from({ length: Math.max(0, fim - offset) }, (_, i) => tx(total - offset - i));
  });
  const p1 = await paginaExtrato(0);
  expect(p1.itens).toHaveLength(PAGINA_EXTRATO);
  expect(p1.proximo).toBe(PAGINA_EXTRATO);
  const p2 = await paginaExtrato(p1.proximo!);
  expect(p2.itens).toHaveLength(50);
  expect(p2.proximo).toBeNull();
  expect(p2.itens.at(-1)?.id).toBe(1); // a mais antiga é alcançável
  expect(get).toHaveBeenCalledWith(
    `/pagamentos/transacoes?limite=${PAGINA_EXTRATO + 1}&offset=100`,
  );
});
