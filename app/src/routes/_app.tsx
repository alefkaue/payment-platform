import { createFileRoute, Link, Navigate, Outlet, useNavigate } from "@tanstack/react-router";
import { Bell, LogOut, Menu, Settings, User, X } from "lucide-react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import { naoLidas } from "@/lib/api";
import { navPrimaria, navSecundaria, type NavItem } from "@/lib/nav";
import { iniciais } from "@/lib/format";
import type { Conta } from "@/lib/types";
import { Wordmark } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app")({ component: AppLayout });

function AppLayout() {
  const { ready, conta, contas, trocarConta, sair } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [mais, setMais] = useState(false);
  const alertas = useQuery({ queryKey: ["nao-lidas", conta?.numero], queryFn: naoLidas });

  if (!ready) return null;
  if (!conta) return <Navigate to="/login" replace />;

  const primaria = navPrimaria(conta.tipo, conta.papel);
  const secundaria = navSecundaria(conta.tipo);
  const trocar = (c: Conta) => {
    trocarConta(c);
    qc.clear(); // dados da conta anterior não podem aparecer na nova
    nav({ to: "/inicio" });
  };
  const sairAgora = () => {
    sair();
    nav({ to: "/login" });
  };
  const naoLidasN = alertas.data ?? 0;

  return (
    // App em formato de celular em qualquer largura: no mobile ocupa a tela toda;
    // no desktop vira uma coluna de telefone centralizada, com fundo escuro nas laterais.
    <div className="flex min-h-[100dvh] justify-center bg-black">
      <div className="relative flex min-h-[100dvh] w-full max-w-[460px] flex-col bg-background shadow-2xl">
        {/* Header */}
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line2 bg-background/95 px-4 py-3 backdrop-blur">
          <Link to="/inicio" aria-label="Início">
            <Wordmark size="sm" />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/notificacoes"
              aria-label="Notificações"
              className="relative grid h-10 w-10 place-items-center rounded-full border border-line2 text-mut2 transition hover:bg-tint hover:text-ink"
            >
              <Bell size={18} />
              {naoLidasN > 0 && (
                <span className="absolute right-2 top-2 grid h-4 min-w-4 place-items-center rounded-full bg-ink px-1 text-[10px] font-bold text-ink-foreground">
                  {naoLidasN}
                </span>
              )}
            </Link>
            <Link
              to="/perfil"
              aria-label="Meu perfil"
              className="grid h-10 w-10 place-items-center rounded-full bg-ink text-xs font-semibold text-ink-foreground"
            >
              {iniciais(conta.nome)}
            </Link>
          </div>
        </header>

        {/* Conteúdo */}
        <main className="flex-1 px-4 pb-28 pt-5">
          {contas.length > 1 && <SeletorConta atual={conta} contas={contas} onTrocar={trocar} />}
          <Outlet />
        </main>

        {/* Barra inferior */}
        <nav
          aria-label="Principal"
          className="fixed bottom-0 left-1/2 z-20 w-full max-w-[460px] -translate-x-1/2 border-t border-line2 bg-background/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur"
        >
          <div className="grid grid-cols-5">
            {primaria.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium text-mut3"
                activeProps={{ className: "text-ink" }}
              >
                <Icon size={20} /> {label}
              </Link>
            ))}
            <button
              onClick={() => setMais(true)}
              className="flex flex-col items-center gap-1 py-2.5 text-[10px] font-medium text-mut3"
            >
              <Menu size={20} /> Mais
            </button>
          </div>
        </nav>

        {mais && (
          <MaisDrawer
            itens={secundaria}
            naoLidas={naoLidasN}
            onFechar={() => setMais(false)}
            onSair={sairAgora}
          />
        )}
      </div>
    </div>
  );
}

/** Menu "Mais" (bottom sheet) no mobile: itens secundários + config + sair. */
function MaisDrawer({
  itens,
  naoLidas,
  onFechar,
  onSair,
}: {
  itens: NavItem[];
  naoLidas: number;
  onFechar: () => void;
  onSair: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-label="Mais opções">
      <button
        aria-label="Fechar"
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        onClick={onFechar}
      />
      <div className="absolute bottom-0 left-1/2 max-h-[85vh] w-full max-w-[460px] -translate-x-1/2 overflow-y-auto rounded-t-[26px] bg-background p-5 pb-8 shadow-lift enter">
        <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line2" />
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">Mais na Astro</h2>
          <button
            onClick={onFechar}
            aria-label="Fechar"
            className="grid h-9 w-9 place-items-center rounded-full border border-line2 text-mut2"
          >
            <X size={18} />
          </button>
        </div>
        <ul className="grid gap-2">
          {itens.map(({ to, label, icon: Icon, hint }) => (
            <li key={to}>
              <Link
                to={to}
                onClick={onFechar}
                className="flex items-center gap-3 rounded-[16px] border border-border bg-card p-3.5 transition hover:bg-tint"
              >
                <span className="relative grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
                  <Icon size={19} />
                  {to === "/notificacoes" && naoLidas > 0 && (
                    <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-ink px-1 text-[10px] font-bold text-ink-foreground">
                      {naoLidas}
                    </span>
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-ink">{label}</span>
                  {hint && <span className="block truncate text-xs text-mut3">{hint}</span>}
                </span>
              </Link>
            </li>
          ))}
          <li>
            <Link
              to="/config"
              onClick={onFechar}
              className="flex items-center gap-3 rounded-[16px] border border-border bg-card p-3.5 transition hover:bg-tint"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
                <Settings size={19} />
              </span>
              <span className="font-medium text-ink">Configurações</span>
            </Link>
          </li>
        </ul>
        <button
          onClick={() => {
            onFechar();
            onSair();
          }}
          className="btn btn-ghost mt-4 w-full gap-2 text-err"
        >
          <LogOut size={18} /> Sair da conta
        </button>
      </div>
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
            className={`flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition ${
              ativa ? "bg-ink text-ink-foreground" : "bg-tint text-mut2 hover:text-ink"
            }`}
          >
            <span
              className={`grid h-6 w-6 place-items-center rounded-full text-[10px] font-bold ${
                ativa ? "bg-ink-foreground/15 text-ink-foreground" : "bg-card text-mut2"
              }`}
            >
              {c.tipo === "PJ" ? iniciais(c.nome) : <User size={13} />}
            </span>
            {c.tipo === "PJ" ? c.nome : "Conta pessoal"}
          </button>
        );
      })}
    </div>
  );
}
