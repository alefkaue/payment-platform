/** A tela guarda esta intenção até receber a confirmação do servidor. */
export function criarIntencaoPagamento() {
  let atual: { assinatura: string; chave: string } | null = null;
  return {
    preparar(assinatura: string): string {
      if (atual?.assinatura !== assinatura) {
        const chave =
          globalThis.crypto?.randomUUID?.() ??
          Array.from(globalThis.crypto.getRandomValues(new Uint8Array(24)), (b) =>
            b.toString(16).padStart(2, "0"),
          ).join("");
        atual = { assinatura, chave };
      }
      return atual.chave;
    },
    concluir() {
      atual = null;
    },
  };
}
