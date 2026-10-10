// Cartões de produto (Loja) e de voo (Viagens), tirados de components/payflow/ui.tsx
// junto com as telas arquivadas. Ver README.md desta pasta.
import { Link } from "@tanstack/react-router";
import { Plane } from "lucide-react";
import { fmtBRL } from "@/lib/format";
import type { Produto, Voo } from "@/lib/types";

export function ProdutoCard({ p }: { p: Produto }) {
  return (
    <Link
      to="/loja/$id"
      params={{ id: String(p.id) }}
      className="surface group flex flex-col overflow-hidden transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <div className="grid aspect-[4/3] place-items-center bg-gradient-to-br from-tint to-tax-bg text-5xl">
        {p.emoji}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <span className="text-xs font-medium text-mut3">{p.categoria}</span>
        <p className="mt-0.5 line-clamp-2 font-semibold text-ink">{p.nome}</p>
        <p className="mt-auto pt-3 text-lg font-semibold tabular text-ink">{fmtBRL(p.preco)}</p>
        <span className="mt-1 inline-flex w-fit items-center gap-1 rounded-full bg-tax-bg px-2 py-0.5 text-[11px] font-medium text-tax2">
          <span className="h-1.5 w-1.5 rounded-full bg-ocre" /> split {p.merchant_nome}
        </span>
      </div>
    </Link>
  );
}

export function VooCard({ v, onSelect }: { v: Voo; onSelect: () => void }) {
  return (
    <div className="surface p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-mut2">
          <Plane size={16} /> {v.companhia}
          {!v.direto && (
            <span className="rounded-full bg-tint px-2 py-0.5 text-[11px] text-mut3">1 parada</span>
          )}
        </div>
        <span className="text-xs text-mut3">{v.duracao}</span>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div className="text-center">
          <p className="text-xl font-semibold tabular text-ink">{v.saida}</p>
          <p className="text-xs text-mut3">{v.origem}</p>
        </div>
        <div className="mx-3 flex-1 border-t border-dashed border-line2" />
        <div className="text-center">
          <p className="text-xl font-semibold tabular text-ink">{v.chegada}</p>
          <p className="text-xs text-mut3">{v.destino}</p>
        </div>
      </div>
      <div className="mt-4 flex items-end justify-between border-t border-border pt-4">
        <div>
          <p className="text-lg font-semibold tabular text-ink">{fmtBRL(v.preco)}</p>
          <p className="text-xs text-mut3">
            ou {new Intl.NumberFormat("pt-BR").format(v.milhas)} pontos
          </p>
        </div>
        <button onClick={onSelect} className="btn btn-ink h-10 px-5 text-sm">
          Selecionar
        </button>
      </div>
    </div>
  );
}
