import { createFileRoute } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { paginaExtrato } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL } from "@/lib/format";
import type { Transacao } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxItem, TxSkeleton } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/extrato")({
  head: () => ({
    meta: [
      { title: "Extrato — Astro" },
      {
        name: "description",
        content: "Todas as suas transações, com o imposto retido em cada uma.",
      },
    ],
  }),
  component: Extrato,
});

type Filtro = "todas" | "entradas" | "saidas" | "imposto";
const FILTROS: { k: Filtro; label: string }[] = [
  { k: "todas", label: "Todas" },
  { k: "entradas", label: "Entradas" },
  { k: "saidas", label: "Saídas" },
  { k: "imposto", label: "Com imposto" },
];

const mesLabel = (iso: string) => {
  const s = new Date(iso).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
};

function Extrato() {
  const { conta } = useAuth();
  const minha = conta?.carteira_id ?? 0;
  // Página a página: operações antigas continuam acessíveis (antes parava nas 100 últimas).
  const q = useInfiniteQuery({
    queryKey: ["transacoes", "extrato"],
    queryFn: ({ pageParam }) => paginaExtrato(pageParam),
    initialPageParam: 0,
    getNextPageParam: (ultima) => ultima.proximo ?? undefined,
  });
  const carregadas = useMemo(() => {
    // Uma operação nova entre duas páginas desloca o offset: não mostra a mesma duas vezes.
    const vistas = new Set<number>();
    return (q.data?.pages ?? [])
      .flatMap((p) => p.itens)
      .filter((t) => !vistas.has(t.id) && Boolean(vistas.add(t.id)));
  }, [q.data]);
  const temMais = Boolean(q.hasNextPage);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [busca, setBusca] = useState("");
  const [pull, setPull] = useState(0);
  const startY = useRef<number | null>(null);

  const { grupos, saldoMes } = useMemo(() => {
    const txs = carregadas;
    const termo = busca.trim().toLowerCase();
    const filtradas = txs.filter((t) => {
      const entrada = t.destino_carteira_id === minha;
      if (filtro === "entradas" && !entrada) return false;
      if (filtro === "saidas" && entrada) return false;
      if (filtro === "imposto" && !t.aplicou_split) return false;
      if (termo && !(t.descricao ?? "").toLowerCase().includes(termo)) return false;
      return true;
    });
    const mapa = new Map<string, Transacao[]>();
    for (const t of filtradas) {
      const k = mesLabel(t.criado_em);
      const arr = mapa.get(k);
      if (arr) arr.push(t);
      else mapa.set(k, [t]);
    }
    // saldo líquido do conjunto filtrado (entradas - saídas)
    const saldo = filtradas.reduce((a, t) => {
      const entrada = t.destino_carteira_id === minha;
      const v = entrada ? (t.aplicou_split ? t.liquido : t.valor_bruto) : t.valor_bruto;
      return a + (entrada ? v : -v);
    }, 0);
    return { grupos: [...mapa.entries()], saldoMes: saldo };
  }, [carregadas, filtro, busca, minha]);

  const vazio = !grupos.length;

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

      {/* Busca */}
      <div className="relative mb-3">
        <Search size={17} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-mut3" />
        <input
          className="field pl-10"
          placeholder="Buscar no extrato"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
      </div>

      {/* Filtros */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {FILTROS.map(({ k, label }) => (
          <button
            key={k}
            onClick={() => setFiltro(k)}
            className={cn(
              "shrink-0 rounded-full px-4 py-1.5 text-sm font-medium transition",
              filtro === k ? "bg-ink text-ink-foreground" : "bg-tint text-mut2 hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {!vazio && (
        <div className="mb-4 flex items-center justify-between rounded-[16px] bg-tint px-4 py-3">
          <span className="text-sm text-mut2">
            Resultado do filtro
            {temMais && (
              <span className="block text-xs text-mut3">
                nas {carregadas.length} operações mais recentes carregadas
              </span>
            )}
          </span>
          <span className={cn("tabular font-semibold", saldoMes >= 0 ? "text-pos" : "text-ink")}>
            {saldoMes >= 0 ? "+" : "−"} {fmtBRL(Math.abs(saldoMes))}
          </span>
        </div>
      )}

      {q.isLoading ? (
        <section className="surface px-5 py-1">
          <TxSkeleton n={6} />
        </section>
      ) : q.isError ? (
        <ErrorBox>Não foi possível carregar o extrato.</ErrorBox>
      ) : vazio ? (
        <section className="surface">
          <Empty
            title={busca || filtro !== "todas" ? "Nada encontrado" : "Extrato vazio"}
            hint={
              busca || filtro !== "todas"
                ? temMais
                  ? `Nada nas ${carregadas.length} operações mais recentes. Carregue as anteriores para continuar buscando.`
                  : "Tente outro termo ou filtro."
                : "Quando você enviar ou receber dinheiro, tudo aparece aqui."
            }
          />
          {temMais && <CarregarMais q={q} />}
        </section>
      ) : (
        <div className="space-y-5">
          {grupos.map(([mes, txs]) => (
            <section key={mes}>
              <h2 className="mb-1.5 px-1 text-xs font-semibold uppercase tracking-wide text-mut3">
                {mes}
              </h2>
              <div className="surface px-5 py-1">
                <ul className="divide-y divide-border">
                  {txs.map((t) => (
                    <TxItem key={t.id} t={t} minha={minha} />
                  ))}
                </ul>
              </div>
            </section>
          ))}
          {temMais && <CarregarMais q={q} />}
        </div>
      )}
    </div>
  );
}

function CarregarMais({
  q,
}: {
  q: { fetchNextPage: () => unknown; isFetchingNextPage: boolean; isFetchNextPageError: boolean };
}) {
  return (
    <div className="px-5 pb-4 text-center">
      <button
        className="btn btn-ghost w-full"
        disabled={q.isFetchingNextPage}
        onClick={() => void q.fetchNextPage()}
      >
        {q.isFetchingNextPage ? "Carregando…" : "Carregar operações anteriores"}
      </button>
      {q.isFetchNextPageError && (
        <p className="mt-2 text-sm text-err">Não foi possível carregar as anteriores.</p>
      )}
    </div>
  );
}
