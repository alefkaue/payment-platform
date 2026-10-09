/**
 * Teste ponta a ponta da camada de dados contra um backend rodando de verdade.
 * Só roda com VITE_API_URL definida e o backend em BIOMETRIA_STUB=1:
 *   (backend)  BIOMETRIA_STUB=1 uvicorn app.main:app --port 8765
 *   (app)      VITE_API_URL=http://localhost:8765 npx vitest run src/lib/api.e2e.test.ts
 */
import { describe, expect, it } from "vitest";

const URL_API = import.meta.env["VITE_API_URL"] as string | undefined;

function cpfValido(): string {
  const n = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10));
  const dv = (base: number[], p0: number) => {
    const r = base.reduce((s, d, i) => s + d * (p0 - i), 0) % 11;
    return r < 2 ? 0 : 11 - r;
  };
  const d1 = dv(n, 10);
  const d2 = dv([...n, d1], 11);
  return [...n, d1, d2].join("");
}

function cnpjValido(): string {
  const n = [...Array.from({ length: 8 }, () => Math.floor(Math.random() * 10)), 0, 0, 0, 1];
  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const dv = (base: number[], pesos: number[]) => {
    const r = base.reduce((s, d, i) => s + d * pesos[i]!, 0) % 11;
    return r < 2 ? 0 : 11 - r;
  };
  const d1 = dv(n, p1);
  const d2 = dv([...n, d1], [6, ...p1]);
  return [...n, d1, d2].join("");
}

// O backend precisa rodar também com KYC_DOCUMENTO_OBRIGATORIO=0 e
// DOCUMENTO_PROVEDOR=stub (o teste não manda foto de documento).
describe.runIf(Boolean(URL_API))("api.ts contra o backend v9", () => {
  it("cadastra pessoa + empresa, troca de conta, cria chave e transfere", async () => {
    const api = await import("./api");
    expect(api.MODO_API).toBe(true);
    const sufixo = Date.now();
    const quadros = ["YQ==", "Yg=="];
    const desafio = await api.pedirDesafio("cadastro");
    const empresa = {
      cnpj: cnpjValido(),
      porte: "PME" as const,
      regime_apuracao: "regular" as const,
      nome_fantasia: "E2E Ltda",
    };
    const c = await api.registrar({
      nome: "Teste Ponta",
      email: `e2e${sufixo}@ex.com`,
      senha: "Cofre-Astro#2026",
      cpf: cpfValido(),
      data_nascimento: "1990-05-04",
      celular: "11987654321",
      documento: null,
      biometria: { desafio_id: desafio.desafio_id, quadros },
    });
    // Sem o rosto não há sessão: a etapa 1 só devolve o desafio do login.
    expect(c.etapa.desafio.modo).toBe("login");
    const { resposta: r, erroEmpresa } = await api.concluirCadastro(
      c.etapa,
      { desafio_id: c.etapa.desafio.desafio_id, quadros },
      empresa,
    );
    expect(erroEmpresa).toBeUndefined();
    expect(r.contas.map((x) => x.tipo).sort()).toEqual(["PF", "PJ"]);
    api.selecionarConta(r.contas.find((x) => x.tipo === "PF")!);
    expect((await api.minhaConta()).saldo).toBe(0);

    const chave = await api.criarChave("aleatoria");
    const destino = await api.consultarDestino(chave.valor);
    expect(destino.nome).toContain("Teste");

    const limites = await api.meusLimites();
    expect(limites.noturno).toBe(1000);

    // Sem saldo: transferência falha com a mensagem do backend
    await expect(api.transferir({ destino: { chave: chave.valor }, valor: 10 })).rejects.toThrow();

    // Loja e Viagens (PF): catálogo vem do backend; sem saldo a compra falha
    expect((await api.listarProdutos()).length).toBe(8);
    expect((await api.buscarVoos("CGH")).length).toBe(1);
    await expect(api.comprarProduto({ produto_id: 4 })).rejects.toThrow(/insuficiente/i);
    await expect(api.resgatarPassagem(2)).rejects.toThrow(/Pontos insuficientes/);
    expect((await api.minhaConta()).pontos).toBe(0);

    const pj = r.contas.find((c) => c.tipo === "PJ")!;
    api.selecionarConta(pj);
    const conta = await api.minhaConta();
    expect(conta.tipo).toBe("PJ");
    expect(conta.papel).toBe("admin");
    const ap = await api.apuracaoPJ();
    expect(ap.imposto_retido).toBe(0);
    const cobs = await api.criarCobranca({ valor: 100, descricao: "Pedido E2E" });
    expect(cobs[0]?.vai_reter_imposto).toBe(false);
    expect((await api.listarCobrancas()).length).toBe(1);
  });
});
