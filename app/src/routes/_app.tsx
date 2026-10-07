import { createFileRoute, Link, Navigate, Outlet, useNavigate } from "@tanstack/react-router";
import {
  Home,
  ArrowUpRight,
  FileText,
  ListOrdered,
  ShoppingBag,
  Plane,
  LogOut,
  type LucideProps,
} from "lucide-react";
import type { ComponentType } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import type { Conta } from "@/lib/types";
import { Wordmark } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app")({ component: AppLayout });

type NavItem = { to: string; label: string; icon: ComponentType<LucideProps> };

// Conta PF (consumidor) e PJ (empresa) têm navegações diferentes — como num banco real.
const NAV_PF: NavItem[] = [
  { to: "/inicio", label: "Início", icon: Home },
  { to: "/loja", label: "Loja", icon: ShoppingBag },
  { to: "/viagens", label: "Viagens", icon: Plane },
  { to: "/extrato", label: "Extrato", icon: ListOrdered },
];
const NAV_PJ: NavItem[] = [
  { to: "/inicio", label: "Início", icon: Home },
  { to: "/transferir", label: "Pagar", icon: ArrowUpRight },
  { to: "/contas", label: "Contas", icon: FileText },
  { to: "/extrato", label: "Extrato", icon: ListOrdered },
];

function AppLayout() {
  const { ready, conta, contas, trocarConta, sair } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  if (!ready) return null;
  if (!conta) return <Navigate to="/login" replace />;

  const items = conta.tipo === "PJ" ? NAV_PJ : NAV_PF;
  const trocar = (c: Conta) => {
    trocarConta(c);
    qc.clear(); // dados da conta anterior não podem aparecer na nova
    nav({ to: "/inicio" });
  };

  return (
    <div className="min-h-screen bg-page md:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line2 px-5 py-8 md:flex">
        <Link to="/inicio" className="px-3">
          <Wordmark />
        </Link>
        <nav className="mt-10 flex flex-col gap-1" aria-label="Principal">
          {items.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="flex items-center gap-3 rounded-[14px] px-3 py-2.5 font-medium text-mut2 transition-colors hover:bg-tint hover:text-ink"
              activeProps={{ className: "bg-card text-ink shadow-soft" }}
            >
              <Icon size={18} /> {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto rounded-[18px] bg-card p-4 shadow-soft">
          <p className="truncate text-sm font-semibold text-ink">{conta.nome}</p>
          <p className="text-xs text-muted-foreground">
            Conta {conta.tipo === "PJ" ? "Empresa (PJ)" : "Pessoa física"}
            {conta.numero ? ` · ${conta.numero}` : ""}
          </p>
          <button
            onClick={() => {
              sair();
              nav({ to: "/login" });
            }}
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-mut2 hover:text-ink"
          >
            <LogOut size={14} /> Sair
          </button>
        </div>
      </aside>

      <main className="mx-auto w-full max-w-3xl px-4 pb-28 pt-6 md:px-10 md:pb-12 md:pt-10">
        {contas.length > 1 && <SeletorConta atual={conta} contas={contas} onTrocar={trocar} />}
        <Outlet />
      </main>

      <nav
        aria-label="Principal"
        className="fixed inset-x-0 bottom-0 z-20 border-t border-line2 bg-background/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        <div className="grid" style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}>
          {items.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium text-mut3"
              activeProps={{ className: "text-ink" }}
            >
              <Icon size={20} /> {label}
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}

/** Troca entre a conta pessoal e as das empresas em que a pessoa tem vínculo. */
function SeletorConta({
  atual,
  contas,
  onTrocar,
}: {
  atual: Conta;
  contas: Conta[];
  onTrocar: (c: Conta) => void;
}) {
  return (
    <div role="tablist" aria-label="Conta em uso" className="mb-5 flex gap-2 overflow-x-auto pb-1">
      {contas.map((c) => {
        const ativa = c.carteira_id === atual.carteira_id;
        return (
          <button
            key={c.carteira_id}
            role="tab"
            aria-selected={ativa}
            onClick={() => !ativa && onTrocar(c)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition ${
              ativa ? "bg-ink text-ink-foreground" : "bg-tint text-mut2 hover:text-ink"
            }`}
          >
            {c.tipo === "PJ" ? c.nome : "Conta pessoal"}
          </button>
        );
      })}
    </div>
  );
}
