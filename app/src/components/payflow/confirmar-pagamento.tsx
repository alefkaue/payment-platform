import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { KeyRound, ShieldCheck, X } from "lucide-react";
import { ApiError, LIMITE_AUTENTICACAO_ADICIONAL, temTotp } from "@/lib/api";
import { fmtBRL } from "@/lib/format";
import { BotaoFinanceiro, useFecharAoVoltar } from "@/lib/mobile";
import type { ConfirmacaoPagamento } from "@/lib/types";
import { ErrorBox, Field } from "./ui";

/** O servidor pediu (ou recusou) o 2º fator: a tela passa a pedir o código. */
function erroDeTotp(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    (e.status === 401 || e.status === 403) &&
    /verifica[cç][aã]o|TOTP/i.test(e.message)
  );
}

/**
 * Confirmação de pagamento no lugar do rosto: senha da conta sempre e, acima de
 * LIMITE_AUTENTICACAO_ADICIONAL (ou em mudança de acesso), o código de 6 dígitos do
 * app autenticador. Quem decide é o servidor; se ele pedir o código, a tela pede.
 */
export function ConfirmarPagamento({
  valor,
  pedeTotp: pedeTotpInicial,
  titulo = "Confirme o pagamento",
  acao = "Confirmar",
  onConfirmar,
  onClose,
}: {
  valor?: number | undefined;
  pedeTotp: boolean;
  titulo?: string;
  acao?: string;
  onConfirmar: (c: ConfirmacaoPagamento) => Promise<unknown>;
  onClose: () => void;
}) {
  useFecharAoVoltar(true, onClose, 50);
  const [senha, setSenha] = useState("");
  const [codigo, setCodigo] = useState("");
  const [pedeTotp, setPedeTotp] = useState(pedeTotpInicial);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const totp = useQuery({ queryKey: ["totp"], queryFn: temTotp, enabled: pedeTotp });
  const semTotp = pedeTotp && totp.data === false;

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (enviando) return;
    setErro(null);
    if (!senha) return setErro("Digite a senha da sua conta.");
    if (pedeTotp && !/^\d{6}$/.test(codigo))
      return setErro("Digite os 6 dígitos do app autenticador.");
    setEnviando(true);
    try {
      await onConfirmar({ senha, ...(pedeTotp ? { codigo_totp: codigo } : {}) });
    } catch (err) {
      setErro((err as Error).message);
      // O código é de uso único: depois de uma tentativa, vale o próximo.
      setCodigo("");
      if (erroDeTotp(err)) {
        setPedeTotp(true);
        void totp.refetch();
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={titulo}>
      <button
        type="button"
        aria-label="Fechar"
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        disabled={enviando}
        onClick={onClose}
      />
      <form
        onSubmit={enviar}
        style={{ paddingBottom: "calc(2rem + env(safe-area-inset-bottom))" }}
        className="absolute bottom-0 left-1/2 max-h-[90vh] w-full max-w-[460px] -translate-x-1/2 space-y-4 overflow-y-auto rounded-t-[26px] bg-background p-5 shadow-lift enter"
      >
        <div className="mx-auto h-1.5 w-10 rounded-full bg-line2" />
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">{titulo}</h2>
            {valor != null && <p className="tabular text-sm text-mut2">Valor: {fmtBRL(valor)}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            aria-label="Fechar"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line2 text-mut2"
          >
            <X size={18} />
          </button>
        </div>

        <Field label="Senha da conta" id="confirmar-senha">
          <input
            id="confirmar-senha"
            type="password"
            autoComplete="current-password"
            className="field"
            autoFocus
            value={senha}
            disabled={enviando}
            onChange={(e) => setSenha(e.target.value)}
          />
        </Field>

        {pedeTotp && (
          <>
            <Field
              label="Código do app autenticador"
              id="confirmar-totp"
              hint={`Acima de ${fmtBRL(LIMITE_AUTENTICACAO_ADICIONAL)} pedimos também o código de 6 dígitos (muda a cada 30 s).`}
            >
              <input
                id="confirmar-totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                className="field tabular tracking-[0.4em]"
                placeholder="000000"
                value={codigo}
                disabled={enviando || semTotp}
                onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
              />
            </Field>
            {semTotp && (
              <p className="flex items-start gap-2 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
                <ShieldCheck size={16} className="mt-0.5 shrink-0" />
                <span>
                  Para pagar acima de {fmtBRL(LIMITE_AUTENTICACAO_ADICIONAL)}, ative antes a
                  verificação em duas etapas.{" "}
                  <Link to="/seguranca" className="font-semibold underline">
                    Ativar agora
                  </Link>
                </span>
              </p>
            )}
          </>
        )}

        {erro && <ErrorBox>{erro}</ErrorBox>}
        <BotaoFinanceiro className="btn btn-ink w-full gap-2" disabled={enviando || semTotp}>
          <KeyRound size={18} /> {enviando ? "Enviando…" : acao}
        </BotaoFinanceiro>
      </form>
    </div>
  );
}
