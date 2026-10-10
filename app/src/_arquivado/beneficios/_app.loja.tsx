import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Lock } from "lucide-react";
import { listarProdutos } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, PageTitle } from "@/components/payflow/ui";
import { ProdutoCard } from "./cartoes-beneficios";

export const Route = createFileRoute("/_app/loja")({
  head: () => ({
    meta: [
      { title: "Loja — Astro" },
      { name: "description", content: "Compre de lojistas parceiros pagando direto do seu saldo." },
    ],
  }),
  component: Loja,
});

function Loja() {
  const { conta } = useAuth();
  const q = useQuery({ queryKey: ["produtos"], queryFn: listarProdutos });
  const [cat, setCat] = useState<string>("Todos");

  const categorias = useMemo(() => {
    const set = new Set((q.data ?? []).map((p) => p.categoria));
    return ["Todos", ...Array.from(set)];
  }, [q.data]);

  const lista = useMemo(
    () => (q.data ?? []).filter((p) => cat === "Todos" || p.categoria === cat),
    [q.data, cat],
  );

  if (conta?.tipo === "PJ") {
    return (
      <div className="enter">
        <PageTitle>Loja</PageTitle>
        <div className="surface flex items-start gap-3 p-6">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-mut2">
            <Lock size={18} />
          </div>
          <div>
            <p className="font-semibold text-ink">Exclusivo para contas Pessoa Física.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Sua conta é empresa (PJ) — você recebe as compras com o split já aplicado.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="enter">
      <PageTitle sub="Pague direto do saldo. Como o lojista é PJ, o imposto é retido no ato.">
        Loja
      </PageTitle>

      <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
        {categorias.map((c) => (
          <button
            key={c}
            onClick={() => setCat(c)}
            className={cn(
              "shrink-0 rounded-full px-4 py-2 text-sm font-medium transition",
              cat === c ? "bg-ink text-ink-foreground" : "bg-tint text-mut2 hover:text-ink",
            )}
          >
            {c}
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aspect-[3/4] animate-pulse rounded-[20px] bg-tint" />
          ))}
        </div>
      ) : q.isError ? (
        <ErrorBox>Não foi possível carregar a loja.</ErrorBox>
      ) : !lista.length ? (
        <Empty title="Nenhum produto nesta categoria" />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          {lista.map((p) => (
            <ProdutoCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </div>
  );
}
