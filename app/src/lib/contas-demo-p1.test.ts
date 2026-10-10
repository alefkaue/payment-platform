import { expect, it } from "vitest";
import { listarFaturas } from "./api";
import { cobrancasDemo, contasDemo, sessao } from "@/mocks/data";
import type { Cobranca } from "./types";

it("demo preserva estados, vencimento real e exclui canceladas/estornadas", async () => {
  sessao.conta = { ...contasDemo.PJ, carteira_id: 99001 };
  const criadas: Cobranca[] = (["aberta", "paga", "cancelada", "estornada"] as const).map(
    (status, id) => ({
      id,
      txid: String(id),
      status,
      valor: 100,
      cbs: 1,
      ibs: 0,
      vai_reter_imposto: true,
      vencimento: id === 0 ? "2026-10-20" : null,
      descricao: "Cliente",
      nfe_chave: null,
      pix_copia_e_cola: "demo",
      linha_digitavel: "demo",
      parcela_numero: 1,
      parcelas_total: 1,
      recebedor_carteira_id: 99001,
    }),
  );
  cobrancasDemo.push(...criadas);
  try {
    const lista = await listarFaturas();
    expect(lista).toHaveLength(2);
    expect(lista.find((f) => f.status === "pendente")).toMatchObject({
      liquido: 99,
      vencimento: "2026-10-20",
    });
    expect(lista.find((f) => f.status === "liquidado")).toMatchObject({
      liquido: 99,
      vencimento: "",
    });
  } finally {
    cobrancasDemo.splice(cobrancasDemo.indexOf(criadas[0]!), criadas.length);
  }
});
