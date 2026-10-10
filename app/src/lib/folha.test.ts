import { beforeEach, describe, expect, it } from "vitest";
import {
  cadastrarFuncionario,
  decidirPendente,
  funcionarios,
  pagarFolha,
  pendentes,
  removerFuncionario,
  transacaoPorId,
  transacoes,
} from "./api";
import { centavosFolha, totalFolha } from "./folha";
import { contasDemo, sessao } from "@/mocks/data";
import { contaPorId } from "@/mocks/banco";

const bio = { desafio_id: "demo", quadros: [] };
let idConta = 80000;
beforeEach(() => {
  localStorage.clear();
  sessao.conta = {
    ...contasDemo.PJ,
    carteira_id: ++idConta,
    numero: String(idConta),
    porte: "PME",
    saldo: 10000,
  };
});
async function cadastrar(salario = "100.00") {
  return cadastrarFuncionario({
    nome: "Ana Fictícia",
    cpf: "52998224725",
    cargo: "Atendimento",
    salario,
  });
}
describe("folha em demonstração", () => {
  it("cadastra com dinheiro decimal e CPF mascarado; remove com isolamento por empresa", async () => {
    expect(await funcionarios()).toEqual([]);
    const f = await cadastrar();
    expect(f).toMatchObject({ nome: "Ana Fictícia", cpf: "***.982.247-**", salario: "100.00" });
    const lista = await funcionarios();
    lista[0]!.nome = "Alterado";
    expect((await funcionarios())[0]?.nome).toBe("Ana Fictícia");
    const anterior = sessao.conta;
    sessao.conta = { ...anterior, carteira_id: ++idConta };
    expect(await funcionarios()).toEqual([]);
    await expect(removerFuncionario(f.id)).rejects.toThrow(/não encontrado/);
    sessao.conta = anterior;
    await removerFuncionario(f.id);
    expect(await funcionarios()).toEqual([]);
  });
  it("paga o salário, credita a PF e grava transação consultável no extrato e comprovante", async () => {
    const pf = contaPorId(contasDemo.PF.carteira_id)?.saldo;
    const f = await cadastrar("100.10");
    const pontos = sessao.conta.pontos;
    const resultado = await pagarFolha([{ funcionario_id: f.id }]);
    expect(resultado).toMatchObject({
      resultados: [{ situacao: "pago", funcionario_id: f.id }],
    });
    expect(sessao.conta.saldo).toBe(9899.9);
    expect(sessao.conta.pontos).toBe(pontos);
    expect(contaPorId(contasDemo.PF.carteira_id)?.saldo).toBeCloseTo(pf! + 100.1);
    if (!("resultados" in resultado)) throw new Error("Esperava pagamento.");
    const id = resultado.resultados[0]!.transacao_id!;
    expect(await transacaoPorId(id)).toMatchObject({
      id,
      valor_bruto: 100.1,
      aplicou_split: false,
      status: "concluida",
    });
    expect((await transacoes()).some((t) => t.id === id)).toBe(true);
    const empresa = sessao.conta;
    sessao.conta = contaPorId(contasDemo.PF.carteira_id)!;
    expect((await transacoes()).some((t) => t.id === id)).toBe(true);
    expect(await transacaoPorId(id)).toMatchObject({
      destino_carteira_id: sessao.conta.carteira_id,
    });
    sessao.conta = empresa;
    await pagarFolha([{ funcionario_id: f.id, valor: "0.20" }]);
    expect(sessao.conta.saldo).toBe(9899.7);
  });
  it("pede rosto só acima de 500 e recusa saldo insuficiente", async () => {
    const f = await cadastrar("500.00");
    await pagarFolha([{ funcionario_id: f.id }]);
    await expect(pagarFolha([{ funcionario_id: f.id, valor: "500.01" }])).rejects.toThrow(/rosto/);
    expect(sessao.conta.saldo).toBe(9500);
    await pagarFolha([{ funcionario_id: f.id, valor: "500.01" }], "Salário", bio);
    await expect(
      pagarFolha([{ funcionario_id: f.id, valor: "9999.00" }], undefined, bio),
    ).rejects.toThrow(/Saldo insuficiente/);
  });
  it("alçada por operação e diária geram pendência sem débito", async () => {
    const f = await cadastrar("100.00");
    sessao.conta.papel = "operador";
    sessao.conta.alcada = 150;
    await pagarFolha([{ funcionario_id: f.id }]);
    const r = await pagarFolha([{ funcionario_id: f.id }]);
    expect(r).toHaveProperty("pendente");
    expect(sessao.conta.saldo).toBe(9900);
    expect(await pagarFolha([{ funcionario_id: f.id, valor: "5000.00" }])).toHaveProperty(
      "pendente",
    );
    expect(await pendentes()).toHaveLength(2);
    sessao.conta = { ...sessao.conta, carteira_id: ++idConta };
    expect(await pendentes()).toEqual([]);
  });
  it("assinatura conjunta da Grande vale para admin e registra a primeira assinatura", async () => {
    const f = await cadastrar("250000.00");
    sessao.conta.porte = "GRANDE";
    expect(await pagarFolha([{ funcionario_id: f.id }])).toMatchObject({
      pendente: { valor: "250000.00", aprovacoes_necessarias: 2 },
    });
    expect(sessao.conta.saldo).toBe(10000);
    expect((await pendentes())[0]?.aprovadores).toEqual(["Você"]);
  });
  it("recusa PF, consulta e gestão por operador", async () => {
    const f = await cadastrar();
    sessao.conta.papel = "operador";
    await expect(cadastrar()).rejects.toThrow(/papel/);
    await expect(removerFuncionario(f.id)).rejects.toThrow(/papel/);
    sessao.conta.papel = "consulta";
    await expect(funcionarios()).rejects.toThrow(/papel/);
    await expect(pagarFolha([{ funcionario_id: f.id }])).rejects.toThrow(/papel/);
    sessao.conta.tipo = "PF";
    await expect(funcionarios()).rejects.toThrow(/empresas/);
  });
  it("recusa folha vazia, repetidos, desconhecidos e valores inválidos sem débito", async () => {
    const f = await cadastrar();
    await expect(pagarFolha([])).rejects.toThrow(/Selecione/);
    await expect(pagarFolha([{ funcionario_id: f.id }, { funcionario_id: f.id }])).rejects.toThrow(
      /repetido/,
    );
    await expect(pagarFolha([{ funcionario_id: -1 }])).rejects.toThrow(/não encontrado/);
    for (const valor of ["0", "-1", "NaN", "1.001", "Infinity"])
      await expect(pagarFolha([{ funcionario_id: f.id, valor }])).rejects.toThrow();
    expect(sessao.conta.saldo).toBe(10000);
  });
  it("respeita o limite de um funcionário no MEI", async () => {
    sessao.conta.porte = "MEI";
    await cadastrar();
    await expect(
      cadastrarFuncionario({ nome: "Bruno Fictício", cpf: "11144477735" }),
    ).rejects.toThrow(/MEI/);
  });
  it("a prévia soma decimais sem arredondamento binário", () => {
    expect(totalFolha(["0.10", "0,20", "100.01"])).toBe("100.31");
    expect(centavosFolha("500.01")).toBe(50001n);
    expect(() => totalFolha(["1.001"])).toThrow();
  });
  it("recusa CPF inválido e duplicado e aceita salário não informado", async () => {
    await expect(
      cadastrarFuncionario({ nome: "Ana Fictícia", cpf: "11111111111" }),
    ).rejects.toThrow(/CPF/);
    const f = await cadastrarFuncionario({ nome: "Ana Fictícia", cpf: "52998224725" });
    expect(f.salario).toBeNull();
    await expect(cadastrar()).rejects.toThrow(/já cadastrado/);
    await expect(pagarFolha([{ funcionario_id: f.id }])).rejects.toThrow(/Informe o valor/);
    await pagarFolha([{ funcionario_id: f.id, valor: "10.00" }]);
    expect(sessao.conta.saldo).toBe(9990);
  });
  it("quem lançou cancela a própria pendência e não pode aprová-la", async () => {
    const f = await cadastrar();
    sessao.conta.papel = "operador";
    sessao.conta.alcada = 0;
    const r = await pagarFolha([{ funcionario_id: f.id }]);
    if (!("pendente" in r)) throw new Error("Esperava uma pendência.");
    await expect(decidirPendente(r.pendente.id, true, bio)).rejects.toThrow(/própria operação/);
    expect(await decidirPendente(r.pendente.id, false)).toMatchObject({
      status: "recusada",
      mensagem: "Folha cancelada.",
    });
    expect(sessao.conta.saldo).toBe(10000);
  });
  it("funcionário sem conta Astro retorna erro sem débito ou transação; lote misto paga só quem tem conta", async () => {
    const semConta = await cadastrarFuncionario({
      nome: "Sem Conta",
      cpf: "11144477735",
      salario: "200.00",
    });
    expect(await pagarFolha([{ funcionario_id: semConta.id }])).toEqual({
      resultados: [{ funcionario_id: semConta.id, situacao: "erro", erro: "sem conta Astro" }],
    });
    expect(sessao.conta.saldo).toBe(10000);
    expect(await transacoes()).toEqual([]);
    const comConta = await cadastrar();
    expect(
      await pagarFolha([{ funcionario_id: semConta.id }, { funcionario_id: comConta.id }]),
    ).toMatchObject({ resultados: [{ situacao: "erro" }, { situacao: "pago" }] });
    expect(sessao.conta.saldo).toBe(9900);
    expect(await transacoes()).toHaveLength(1);
    expect(contaPorId(sessao.conta.carteira_id)?.saldo).toBe(9900);
  });
});
