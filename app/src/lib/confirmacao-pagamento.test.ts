/**
 * Pagamento confirmado por SENHA (sempre) + TOTP acima de R$ 5.000 — sem rosto.
 * Espelha backend/tests (matriz senha/TOTP) no modo demonstração, confere o corpo
 * enviado à API e a implementação TOTP (RFC 6238).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  aprovacaoPedeTotp,
  concluirCadastro,
  confirmarTotp,
  consultarDestino,
  depositar,
  iniciarTotp,
  pedeTotp,
  registrar,
  temTotp,
  transferir,
} from "./api";
import { codigoDoPasso, codigoTotp, passoAtual, passoDoCodigo, PASSO_SEG } from "./totp";
import type { OperacaoPendente } from "./types";

const bio = { desafio_id: "demo", quadros: [] };
const dados = { data_nascimento: "1990-05-04", celular: "11987654321", documento: null };
const SENHA = "Cofre-Astro#2026";

async function cadastrar(nome: string, email: string, cpf: string) {
  const c = await registrar({ nome, email, senha: SENHA, cpf, biometria: bio, ...dados });
  return (await concluirCadastro(c.etapa, bio)).resposta;
}

describe("TOTP (RFC 6238)", () => {
  it("bate com os vetores de teste da RFC (SHA-1)", async () => {
    const chave = new TextEncoder().encode("12345678901234567890");
    // Apêndice B da RFC 6238: T = 59 s, 1111111109 s e 20000000000 s (8 dígitos).
    expect(await codigoDoPasso(chave, Math.floor(59 / 30), 8)).toBe("94287082");
    expect(await codigoDoPasso(chave, Math.floor(1111111109 / 30), 8)).toBe("07081804");
    expect(await codigoDoPasso(chave, Math.floor(20000000000 / 30), 8)).toBe("65353130");
  });

  it("aceita o passo anterior e o seguinte, e mais nada", async () => {
    const segredo = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
    const agora = 1_800_000_000_000;
    const atual = passoAtual(agora);
    for (const d of [-1, 0, 1]) {
      const codigo = await codigoTotp(segredo, agora + d * PASSO_SEG * 1000);
      expect(await passoDoCodigo(segredo, codigo, agora)).toBe(atual + d);
    }
    const velho = await codigoTotp(segredo, agora - 3 * PASSO_SEG * 1000);
    expect(await passoDoCodigo(segredo, velho, agora)).toBeNull();
    expect(await passoDoCodigo(segredo, "12a456", agora)).toBeNull();
  });
});

describe("regra do limite", () => {
  it("TOTP só acima de R$ 5.000,00; em acesso, sempre", () => {
    expect(pedeTotp(5000)).toBe(false);
    expect(pedeTotp(5000.01)).toBe(true);
    const op = { tipo: "folha", valor: 100 } as OperacaoPendente;
    expect(aprovacaoPedeTotp(op)).toBe(false);
    expect(aprovacaoPedeTotp({ ...op, tipo: "acesso" })).toBe(true);
    expect(aprovacaoPedeTotp({ ...op, valor: 5000.01 })).toBe(true);
  });
});

describe("modo demonstração: senha + TOTP", () => {
  beforeEach(() => localStorage.clear());

  it("senha sempre; TOTP acima do limite, ativado pelo app autenticador e de uso único", async () => {
    const ana = await cadastrar("Ana Souza", "ana@exemplo.com", "39053344705");
    await cadastrar("Beatriz Lima", "bia@exemplo.com", "11144477735");
    await depositar({ valor: 10000 });
    await depositar({ valor: 10000 });
    const { destino } = await consultarDestino(String(ana.conta.carteira_id));
    const pix = (valor: number, confirmacao?: { senha: string; codigo_totp?: string }) =>
      transferir({ destino: destino!, valor, ...(confirmacao ? { confirmacao } : {}) });

    await expect(pix(10)).rejects.toMatchObject({ status: 401 });
    await expect(pix(10, { senha: "errada-123" })).rejects.toMatchObject({ status: 401 });
    expect((await pix(10, { senha: SENHA })).tipo).toBe("transacao");
    expect((await pix(5000, { senha: SENHA })).tipo).toBe("transacao");

    // Acima do limite sem TOTP ativo: 403, nada sai.
    expect(await temTotp()).toBe(false);
    await expect(pix(5000.01, { senha: SENHA })).rejects.toMatchObject({ status: 403 });

    // Ativação: o segredo provisório só vale depois de confirmar um código.
    const { segredo, uri } = await iniciarTotp();
    expect(uri).toContain(`secret=${segredo}`);
    expect(uri).toContain("issuer=ASTRO");
    await expect(confirmarTotp("12345")).rejects.toMatchObject({ status: 400 });
    expect(await temTotp()).toBe(false);
    const agora = Date.now();
    vi.useFakeTimers({ now: agora, toFake: ["Date"] });
    try {
      const daAtivacao = await codigoTotp(segredo);
      await confirmarTotp(daAtivacao);
      expect(await temTotp()).toBe(true);
      // O código usado na ativação não paga nada (anti-replay).
      await expect(pix(6000, { senha: SENHA, codigo_totp: daAtivacao })).rejects.toMatchObject({
        status: 401,
      });
      vi.setSystemTime(agora + PASSO_SEG * 1000);
      const codigo = await codigoTotp(segredo);
      await expect(pix(6000, { senha: "errada-123", codigo_totp: codigo })).rejects.toMatchObject({
        status: 401,
        message: "Senha incorreta.",
      });
      await expect(pix(6000, { senha: SENHA })).rejects.toMatchObject({ status: 401 });
      expect((await pix(6000, { senha: SENHA, codigo_totp: codigo })).tipo).toBe("transacao");
      await expect(pix(6000, { senha: SENHA, codigo_totp: codigo })).rejects.toThrow(
        /já utilizado/,
      );
    } finally {
      vi.useRealTimers();
    }
  }, 30_000);
});
