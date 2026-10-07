import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock, ScanFace, X } from "lucide-react";
import { decidirPendente, pendentes } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData } from "@/lib/format";
import type { OperacaoPendente } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/pendentes")({
  head: () => ({ meta: [{ title: "Aprovações — Astro" }] }),
  component: Pendentes,
});

function Pendentes() {
  const { conta } = useAuth();
  const q = useQuery({ queryKey: ["pendentes", conta?.numero], queryFn: pendentes });

  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  const aguardando = q.data?.filter((o) => o.status === "aguardando") ?? [];
  const decididas = q.data?.filter((o) => o.status !== "aguardando") ?? [];
  const podeAprovar = conta?.papel === "admin" || conta?.papel === "aprovador";

  return (
    <div className="enter">
      <PageTitle sub="Pagamentos acima da alçada de quem lançou, aguardando um segundo aprovador.">
        Aprovações pendentes
      </PageTitle>

      {!podeAprovar && (
        <p className="mb-5 rounded-[16px] bg-tint px-4 py-3 text-sm text-mut2">
          Seu papel não aprova operações. Apenas administradores e aprovadores decidem.
        </p>
      )}

      {q.isLoading ? (
        <div className="surface px-5 py-2">
          <TxSkeleton n={3} />
        </div>
      ) : q.isError ? (
        <ErrorBox>Não foi possível carregar as aprovações.</ErrorBox>
      ) : !aguardando.length && !decididas.length ? (
        <div className="surface">
          <Empty title="Nada para aprovar" hint="Operações acima da alçada aparecem aqui." />
        </div>
      ) : (
        <div className="space-y-4">
          {aguardando.map((o) => (
            <Card key={o.id} o={o} podeAprovar={podeAprovar} />
          ))}
          {decididas.length > 0 && (
            <>
              <h2 className="pt-2 text-sm font-semibold uppercase tracking-wide text-mut3">
                Decididas
              </h2>
              {decididas.map((o) => (
                <Card key={o.id} o={o} podeAprovar={false} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Card({ o, podeAprovar }: { o: OperacaoPendente; podeAprovar: boolean }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: (aprovar: boolean) => decidirPendente(o.id, aprovar),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pendentes"] });
      void qc.invalidateQueries({ queryKey: ["nao-lidas"] });
    },
  });
  const decidida = o.status !== "aguardando";

  return (
    <section className={cn("surface p-5", decidida && "opacity-80")}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-semibold text-ink">{o.contraparte}</p>
          <p className="text-sm text-mut2">{o.descricao}</p>
          <p className="mt-1 text-xs text-mut3">
            Lançado por {o.criado_por} · {fmtData(o.criado_em)}
          </p>
        </div>
        <p className="tabular shrink-0 text-xl font-semibold text-ink">{fmtBRL(o.valor)}</p>
      </div>

      {o.status === "aguardando" ? (
        <>
          <div className="mt-3 flex items-center gap-1.5 text-xs font-medium text-tax2">
            <Clock size={13} /> Aguardando 2º aprovador
          </div>
          {podeAprovar && (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                className="btn btn-ghost gap-2 text-err"
                disabled={mut.isPending}
                onClick={() => mut.mutate(false)}
              >
                <X size={18} /> Recusar
              </button>
              <button
                className="btn btn-ink gap-2"
                disabled={mut.isPending}
                onClick={() => mut.mutate(true)}
              >
                <ScanFace size={18} /> {mut.isPending ? "Enviando…" : "Aprovar"}
              </button>
            </div>
          )}
          {mut.isError && (
            <div className="mt-3">
              <ErrorBox>{(mut.error as Error).message}</ErrorBox>
            </div>
          )}
        </>
      ) : (
        <div
          className={cn(
            "mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
            o.status === "aprovada"
              ? "bg-[color-mix(in_oklab,var(--pos)_14%,transparent)] text-pos"
              : "bg-err-bg text-err",
          )}
        >
          {o.status === "aprovada" ? <Check size={13} /> : <X size={13} />}
          {o.status === "aprovada" ? "Aprovada" : "Recusada"}
        </div>
      )}
    </section>
  );
}
