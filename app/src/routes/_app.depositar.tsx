import { BotaoFinanceiro } from "@/lib/mobile";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check } from "lucide-react";
import { depositar } from "@/lib/api";
import { fmtBRL, parseValor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ErrorBox, Field, PageTitle } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/depositar")({
  head: () => ({ meta: [{ title: "Depositar — Astro" }] }),
  component: Depositar,
});

const ATALHOS = [50, 100, 250, 500];

/**
 * Depósito: no modo demonstração e num servidor de demonstração (DEPOSITO_DEMO=1)
 * o dinheiro de teste entra na hora. Num servidor real o backend recusa e a
 * mensagem explica que o dinheiro entra por Pix para uma chave da conta.
 */
function Depositar() {
  return <DepositoDemo />;
}

function DepositoDemo() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [valorStr, setValorStr] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState(false);

  const valor = parseValor(valorStr);

  async function confirmar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!(valor > 0)) return setErro("Informe um valor válido.");
    setLoading(true);
    try {
      await depositar({ valor });
      qc.invalidateQueries();
      setOk(true);
      setTimeout(() => nav({ to: "/inicio" }), 1100);
    } catch (e2) {
      setErro((e2 as Error).message);
      setLoading(false);
    }
  }

  if (ok) {
    return (
      <div className="enter mx-auto max-w-md pt-10 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-tint text-pos">
          <Check size={28} strokeWidth={2.5} />
        </div>
        <h1 className="mt-5 text-2xl text-ink">Depósito confirmado</h1>
        <p className="tabular mt-2 text-4xl font-semibold tracking-display text-ink">
          {fmtBRL(valor)}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">Voltando ao início…</p>
      </div>
    );
  }

  return (
    <div className="enter mx-auto max-w-md">
      <PageTitle sub="Adicione saldo via Pix para pagar, comprar e transferir.">
        Depositar
      </PageTitle>
      <form onSubmit={confirmar} className="surface space-y-4 p-5 md:p-7">
        <Field label="Valor (R$)" id="valor">
          <input
            autoComplete="off"
            id="valor"
            inputMode="decimal"
            autoFocus
            className="field tabular text-lg"
            value={valorStr}
            onChange={(e) => setValorStr(e.target.value)}
            placeholder="0,00"
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          {ATALHOS.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setValorStr(String(v))}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition",
                valor === v ? "bg-ink text-ink-foreground" : "bg-tint text-mut2 hover:text-ink",
              )}
            >
              {fmtBRL(v)}
            </button>
          ))}
        </div>
        {erro && <ErrorBox>{erro}</ErrorBox>}
        <BotaoFinanceiro className="btn btn-ink w-full" disabled={loading}>
          {loading ? "Depositando…" : "Depositar"}
        </BotaoFinanceiro>
      </form>
    </div>
  );
}
