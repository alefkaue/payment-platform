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

describe.runIf(Boolean(URL_API))("api.ts contra o backend v7", () => {
  it("cadastra pessoa + empresa, troca de conta, cria chave e transfere", async () => {
    const api = await import("./api");
    expect(api.MODO_API).toBe(true);
    const sufixo = Date.now();
    const desafio = await api.pedirDesafio();
    const r = await api.registrar({
      nome: "Teste Ponta",
      email: `e2e${sufixo}@ex.com`,
      senha: "senha12345",
      cpf: cpfValido(),
      biometria: { desafio_id: desafio.desafio_id, quadros: ["YQ==", "Yg=="] },
      empresa: { cnpj: cnpjValido(), porte: "PME", regime_apuracao: "regular", nome_fantasia: "E2E Ltda" },
    });
    expect(r.contas.map((c) => c.tipo).sort()).toEqual(["PF", "PJ"]);
    expect(r.conta.saldo).toBe(0);

    const chave = await api.criarChave("aleatoria");
    const destino = await api.consultarDestino(chave.valor);
    expect(destino.nome).toContain("Teste");

    const limites = await api.meusLimites();
    expect(limites.noturno).toBe(1000);

    // Sem saldo: transferência falha com a mensagem do backend
    await expect(api.transferir({ destino: { chave: chave.valor }, valor: 10 })).rejects.toThrow();

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
