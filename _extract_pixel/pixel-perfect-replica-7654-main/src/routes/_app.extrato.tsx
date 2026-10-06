import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useRef, useState } from "react";
import { transacoes } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Empty, ErrorBox, PageTitle, TxItem, TxSkeleton } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/extrato")({
  head: () => ({
    meta: [
      { title: "Extrato — PayFlow" },
      {
        name: "description",
        content: "Todas as suas transações, com o imposto retido em cada uma.",
      },
      { property: "og:title", content: "Extrato — PayFlow" },
      { property: "og:description", content: "Todas as suas transações." },
    ],
  }),
  component: Extrato,
});

function Extrato() {
  const { conta } = useAuth();
  const q = useQuery({ queryKey: ["transacoes"], queryFn: transacoes });
  const [pull, setPull] = useState(0);
  const startY = useRef<number | null>(null);

  return (
    <div
      className="enter"
      onTouchStart={(e) => {
        if (window.scrollY === 0) startY.current = e.touches[0]?.clientY ?? null;
      }}
      onTouchMove={(e) => {
        const y = e.touches[0]?.clientY;
        if (startY.current !== null && y !== undefined)
          setPull(Math.max(0, Math.min(80, y - startY.current)));
      }}
      onTouchEnd={() => {
        if (pull > 60) q.refetch();
        setPull(0);
        startY.current = null;
      }}
    >
      <div
        className="flex justify-center overflow-hidden transition-[height] duration-200"
        style={{ height: pull ? pull * 0.6 : q.isRefetching ? 36 : 0 }}
      >
        <RefreshCw
          size={18}
          className={cn("mt-2 text-mut2", q.isRefetching && "animate-spin")}
          style={{ transform: `rotate(${pull * 3}deg)` }}
        />
      </div>
      <div className="flex items-start justify-between gap-4">
        <PageTitle sub="Enviadas e recebidas, com o imposto de cada uma.">Extrato</PageTitle>
        <button
          onClick={() => q.refetch()}
          className="btn btn-ghost h-10 px-3"
          aria-label="Atualizar"
        >
          <RefreshCw size={16} className={cn(q.isRefetching && "animate-spin")} />
        </button>
      </div>
      <section className="surface px-5 py-1 md:px-6">
        {q.isLoading ? (
          <TxSkeleton n={6} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>Não foi possível carregar o extrato.</ErrorBox>
          </div>
        ) : !q.data?.length ? (
          <Empty
            title="Extrato vazio"
            hint="Quando você enviar ou receber dinheiro, tudo aparece aqui."
          />
        ) : (
          <ul className="divide-y divide-border">
            {q.data.map((t) => (
              <TxItem key={t.id} t={t} minha={conta?.carteira_id ?? 0} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
