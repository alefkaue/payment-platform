import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { FileText } from "lucide-react";
import { listarFaturas } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL } from "@/lib/format";
import type { DirecaoFatura } from "@/lib/types";
import { Empty, ErrorBox, MetricTile, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { FaturaRow } from "./_app.inicio";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/contas")({
  head: () => ({ meta: [{ title: "Contas — PayFlow" }] }),
  component: Contas,
});

function Contas() {
  const { conta } = useAuth();
  const [aba, setAba] = useState<DirecaoFatura>("receber");
  const q = useQuery({ queryKey: ["faturas"], queryFn: () => listarFaturas() });

  // Contas a pagar/receber são um recurso da conta Empresa.
  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  const todas = q.data ?? [];
  const aReceber = todas.filter((f) => f.direcao === "receber");
  const aPagar = todas.filter((f) => f.direcao === "pagar");
  const totReceber = aReceber.reduce((a, f) => a + f.liquido, 0);
  const totPagar = aPagar.reduce((a, f) => a + f.valor_bruto, 0);
  const totCredito = aPagar.reduce((a, f) => a + f.credito_gerado, 0);
  const lista = aba === "receber" ? aReceber : aPagar;

  return (
    <div className="enter">
      <PageTitle sub="Faturas B2B conciliadas com a nota fiscal (NF-e). O imposto é separado no ato.">
        Contas
      </PageTitle>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricTile label="A receber (líquido)" value={fmtBRL(totReceber)} tone="pos" />
        <MetricTile label="A pagar" value={fmtBRL(totPagar)} />
        <MetricTile
          label="Crédito a gerar"
          value={fmtBRL(totCredito)}
          tone="tax"
          hint="abate impostos futuros"
        />
      </div>

      <div role="tablist" className="mt-6 grid grid-cols-2 rounded-full bg-tint p-1">
        {(["receber", "pagar"] as const).map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={aba === d}
            onClick={() => setAba(d)}
            className={cn(
              "h-10 rounded-full text-sm font-semibold transition-colors duration-200",
              aba === d ? "bg-card text-ink shadow-soft" : "text-mut2 hover:text-ink",
            )}
          >
            {d === "receber" ? "A receber" : "A pagar"}
          </button>
        ))}
      </div>

      <section className="surface mt-4 px-5 py-2">
        {q.isLoading ? (
          <TxSkeleton n={4} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>Não foi possível carregar as contas.</ErrorBox>
          </div>
        ) : !lista.length ? (
          <Empty title="Nada por aqui" hint="As faturas aparecerão aqui." />
        ) : (
          <ul className="divide-y divide-border">
            {lista.map((f) => (
              <FaturaRow key={f.id} f={f} />
            ))}
          </ul>
        )}
      </section>

      <div className="mt-4 flex items-start gap-3 rounded-[16px] bg-tax-bg px-4 py-3.5 text-sm text-tax2">
        <FileText size={18} className="mt-0.5 shrink-0" />
        <p>
          {aba === "receber"
            ? "Cada recebimento é conciliado com a NF-e e o IBS/CBS é separado no ato — você recebe o líquido, sem apurar depois."
            : "Toda compra de insumo gera crédito de IBS/CBS automaticamente, que abate o imposto das suas próximas vendas."}
        </p>
      </div>
    </div>
  );
}
