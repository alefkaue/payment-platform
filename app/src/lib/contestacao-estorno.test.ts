import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  contestar,
  estornarCobranca,
  listarFaturas,
  minhaConta,
  selecionarConta,
  transacaoPorId,
} from "./api";
import { banco, guardarConta, guardarTransacao, salvar, todasTransacoes } from "@/mocks/banco";
import { cobrancasDemo, contasDemo } from "@/mocks/data";
import type { Transacao } from "./types";

const pagamento = (): Transacao => ({
  id: 99001,
  origem_carteira_id: contasDemo.PF.carteira_id,
  destino_carteira_id: contasDemo.PJ.carteira_id,
  valor_bruto: 150.25,
  liquido: 148.75,
  cbs: 1.35,
  ibs: 0.15,
  aplicou_split: true,
  tipo_destino: "PJ",
  auth_metodo: "senha",
  status: "concluida",
  categoria: "cobranca",
  descricao: "Pedido de peças",
  criado_em: new Date().toISOString(),
});

beforeEach(() => {
  localStorage.clear();
  cobrancasDemo.length = 0;
  guardarTransacao(pagamento());
  selecionarConta(contasDemo.PF);
});

describe("contestação na demonstração", () => {
  it("aceita exatamente 80 dias e recusa um instante além", async () => {
    const agora = Date.now();
    const relogio = vi.spyOn(Date, "now").mockReturnValue(agora);
    try {
      const b = banco();
      b.transacoes = [{ ...pagamento(), criado_em: new Date(agora - 80 * 86400000).toISOString() }];
      salvar(b);
      await contestar(99001, "Motivo válido");
      b.contestacoes = [];
      salvar(b);
      relogio.mockReturnValue(agora + 1);
      await expect(contestar(99001, "Motivo válido")).rejects.toThrow(/Prazo/);
    } finally {
      relogio.mockRestore();
    }
  });
  it("abre uma única contestação persistida sem devolver dinheiro antes da análise", async () => {
    const saldo = (await minhaConta()).saldo;
    await contestar(99001, "Não reconheço este pagamento.");
    expect((await transacaoPorId(99001)).contestacao_aberta).toBe(true);
    expect(banco().contestacoes?.[0]?.motivo).toBe("Não reconheço este pagamento.");
    expect((await minhaConta()).saldo).toBe(saldo);
    await expect(contestar(99001, "Outro motivo")).rejects.toMatchObject({ status: 409 });
    expect(banco().contestacoes).toHaveLength(1);
  });
  it("recusa motivo fora do tamanho permitido", async () => {
    await expect(contestar(99001, "abcd")).rejects.toMatchObject({ status: 422 });
    await expect(contestar(99001, "a".repeat(281))).rejects.toMatchObject({ status: 422 });
    expect(banco().contestacoes).toBeUndefined();
  });
  it("recusa recebimento, prazo vencido, estado devolvido e categoria não elegível", async () => {
    selecionarConta(contasDemo.PJ);
    await expect(contestar(99001, "Motivo válido")).rejects.toMatchObject({ status: 404 });
    selecionarConta(contasDemo.PF);
    for (const mudanca of [
      { criado_em: new Date(Date.now() - 81 * 86400000).toISOString() },
      { status: "devolvida" },
      { categoria: "deposito" as const },
    ]) {
      const b = banco();
      b.transacoes = [{ ...pagamento(), ...mudanca }];
      salvar(b);
      await expect(contestar(99001, "Motivo válido")).rejects.toThrow();
    }
    expect(banco().contestacoes).toBeUndefined();
  });
  it("PJ exige admin e aceita transação retida como o servidor", async () => {
    const b = banco();
    b.transacoes = [
      {
        ...pagamento(),
        origem_carteira_id: contasDemo.PJ.carteira_id,
        destino_carteira_id: contasDemo.PF.carteira_id,
        status: "retida",
      },
    ];
    salvar(b);
    guardarConta({ ...contasDemo.PJ, papel: "operador" });
    selecionarConta(contasDemo.PJ);
    await expect(contestar(99001, "Motivo válido")).rejects.toMatchObject({ status: 403 });
    guardarConta(contasDemo.PJ);
    await contestar(99001, "Motivo válido");
    expect((await transacaoPorId(99001)).contestacao_aberta).toBe(true);
  });
});

function prepararCobranca() {
  cobrancasDemo.push({
    id: 99002,
    txid: "pedido-pago",
    valor: 150.25,
    cbs: 1.35,
    ibs: 0.15,
    transacao_id: 99001,
    recebedor_carteira_id: contasDemo.PJ.carteira_id,
    recebedor_nome: contasDemo.PJ.nome,
    pix_copia_e_cola: "ASTRO-SIMULADO.pedido-pago",
    linha_digitavel: "0".repeat(47),
    status: "paga",
    parcela_numero: 1,
    parcelas_total: 1,
    vai_reter_imposto: true,
  });
  selecionarConta(contasDemo.PJ);
}

describe("estorno na demonstração", () => {
  it("devolve o bruto, registra estorno sem split e atualiza a lista uma única vez", async () => {
    prepararCobranca();
    expect((await listarFaturas()).find((f) => f.txid === "pedido-pago")?.status).toBe("liquidado");
    const antes = banco();
    const saldoPJ = antes.contas[contasDemo.PJ.carteira_id]!.saldo;
    const saldoPF = antes.contas[contasDemo.PF.carteira_id]!.saldo;
    const t = await estornarCobranca("pedido-pago");
    expect(t).toMatchObject({
      categoria: "estorno",
      valor_bruto: 150.25,
      liquido: 150.25,
      aplicou_split: false,
      cbs: 0,
      ibs: 0,
    });
    expect((await minhaConta()).saldo).toBeCloseTo(saldoPJ - 150.25);
    selecionarConta(contasDemo.PF);
    expect((await minhaConta()).saldo).toBeCloseTo(saldoPF + 150.25);
    selecionarConta(contasDemo.PJ);
    expect((await listarFaturas()).some((f) => f.txid === "pedido-pago")).toBe(false);
    await expect(estornarCobranca("pedido-pago")).rejects.toMatchObject({ status: 409 });
    expect(todasTransacoes().filter((x) => x.categoria === "estorno")).toHaveLength(1);
  });
  it("saldo insuficiente mantém cobrança paga e dinheiro intacto", async () => {
    prepararCobranca();
    guardarConta({ ...contasDemo.PJ, saldo: 100 });
    const antes = banco();
    await expect(estornarCobranca("pedido-pago")).rejects.toThrow(/Saldo insuficiente/);
    expect(banco()).toEqual(antes);
    expect(cobrancasDemo[0]?.status).toBe("paga");
  });
  it("recusa não admin, outra empresa, PF e cobrança não paga", async () => {
    prepararCobranca();
    guardarConta({ ...contasDemo.PJ, papel: "aprovador" });
    await expect(estornarCobranca("pedido-pago")).rejects.toMatchObject({ status: 403 });
    guardarConta(contasDemo.PJ);
    cobrancasDemo[0]!.recebedor_carteira_id = 9999;
    await expect(estornarCobranca("pedido-pago")).rejects.toMatchObject({ status: 404 });
    cobrancasDemo[0]!.recebedor_carteira_id = contasDemo.PJ.carteira_id;
    cobrancasDemo[0]!.status = "aberta";
    await expect(estornarCobranca("pedido-pago")).rejects.toMatchObject({ status: 409 });
    selecionarConta(contasDemo.PF);
    await expect(estornarCobranca("pedido-pago")).rejects.toMatchObject({ status: 403 });
  });
});
