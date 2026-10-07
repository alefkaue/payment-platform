import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  Bell,
  FileText,
  Gift,
  Landmark,
  ShieldAlert,
  Wallet,
  type LucideProps,
} from "lucide-react";
import type { ComponentType } from "react";
import { marcarNotificacoesLidas, notificacoes } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtData } from "@/lib/format";
import type { Notificacao, TipoNotificacao } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/notificacoes")({
  head: () => ({ meta: [{ title: "Notificações — Astro" }] }),
  component: Notificacoes,
});

const ICONE: Record<TipoNotificacao, ComponentType<LucideProps>> = {
  pagamento: Wallet,
  cobranca: FileText,
  seguranca: ShieldAlert,
  imposto: Landmark,
  pontos: Gift,
  sistema: Bell,
};

function Notificacoes() {
  const { conta } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notificacoes", conta?.numero], queryFn: notificacoes });
  // Ao abrir a central: guarda quais estavam não lidas (para destacar) e zera o
  // contador do sino. A guarda de ref evita rodar duas vezes no StrictMode.
  const [novas, setNovas] = useState<Set<number>>(new Set());
  const feito = useRef(false);

  useEffect(() => {
    if (feito.current || !q.data) return;
    feito.current = true;
    setNovas(new Set(q.data.filter((n) => !n.lida).map((n) => n.id)));
    void marcarNotificacoesLidas().then(() => qc.invalidateQueries({ queryKey: ["nao-lidas"] }));
  }, [q.data, qc]);

  return (
    <div className="enter">
      <PageTitle sub="Avisos da sua conta: pagamentos, cobranças, segurança e impostos.">
        Notificações
      </PageTitle>

      <section className="surface px-3 py-1 md:px-4">
        {q.isLoading ? (
          <TxSkeleton n={5} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>Não foi possível carregar as notificações.</ErrorBox>
          </div>
        ) : !q.data?.length ? (
          <Empty title="Tudo em dia" hint="Você não tem notificações por enquanto." />
        ) : (
          <ul className="divide-y divide-border">
            {q.data.map((n) => (
              <Item key={n.id} n={n} nova={novas.has(n.id)} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Item({ n, nova }: { n: Notificacao; nova: boolean }) {
  const Icon = ICONE[n.tipo] ?? Bell;
  const conteudo = (
    <div className="flex items-start gap-3 py-4">
      <span
        className={cn(
          "relative mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full",
          n.tipo === "seguranca" ? "bg-err-bg text-err" : "bg-tint text-ink",
        )}
      >
        <Icon size={18} />
        {nova && (
          <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-ink ring-2 ring-card" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("text-ink", nova ? "font-semibold" : "font-medium")}>{n.titulo}</p>
        <p className="mt-0.5 text-sm text-mut2">{n.texto}</p>
        <p className="mt-1 text-xs text-mut3">{fmtData(n.criado_em)}</p>
      </div>
    </div>
  );
  return n.href ? (
    <li>
      <Link to={n.href} className="block px-2 transition hover:bg-tint/50">
        {conteudo}
      </Link>
    </li>
  ) : (
    <li className="px-2">{conteudo}</li>
  );
}
