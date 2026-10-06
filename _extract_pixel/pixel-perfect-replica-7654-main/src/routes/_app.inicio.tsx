import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowUpRight,
  Eye,
  EyeOff,
  ListOrdered,
  Plane,
  Plus,
  ShoppingBag,
  Sparkles,
} from "lucide-react";
import { minhaConta, resumoVendasPJ, transacoes } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtId, fmtPontos } from "@/lib/format";
import {
  Empty,
  ErrorBox,
  PromoCard,
  QuickAction,
  SplitBar,
  TxItem,
  TxSkeleton,
} from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/inicio")({
  head: () => ({
    meta: [
      { title: "Início — PayFlow" },
      { name: "description", content: "Seu dinheiro, com o imposto já resolvido no ato." },
    ],
  }),
  component: Inicio,
});

function Inicio() {
  const { conta: sessaoConta, sair } = useAuth();
  const nav = useNavigate();
  const conta = useQuery({ queryKey: ["conta"], queryFn: minhaConta });
  const [ver, setVer] = useState(true);
  const ehPJ = sessaoConta?.tipo === "PJ";

  return (
    <div className="enter space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Olá,</p>
          <h1 className="text-2xl text-ink">{conta.data?.nome ?? "…"}</h1>
        </div>
        <button
          onClick={() => {
            sair();
            nav({ to: "/login" });
          }}
          className="btn btn-ghost h-10 px-4 text-sm md:hidden"
        >
          Sair
        </button>
      </header>

      {/* Cartão de saldo (estilo neobanco) */}
      <section
        className="rounded-[22px] bg-ink p-6 text-ink-foreground shadow-lift md:p-8"
        aria-label="Saldo"
      >
        {conta.isError ? (
          <p>Não foi possível carregar o saldo.</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <p className="text-sm opacity-60">
                {conta.data
                  ? `Conta ${ehPJ ? "Empresa" : "Pessoa física"} · ${fmtId(conta.data.carteira_id)}`
                  : "Carregando…"}
              </p>
              <button
                onClick={() => setVer((v) => !v)}
                aria-label={ver ? "Ocultar saldo" : "Mostrar saldo"}
                className="text-ink-foreground/70 hover:text-ink-foreground"
              >
                {ver ? <Eye size={18} /> : <EyeOff size={18} />}
              </button>
            </div>
            <p className="tabular mt-3 text-[2.5rem] font-semibold leading-none tracking-display md:text-5xl">
              {conta.data ? (
                ver ? (
                  fmtBRL(conta.data.saldo)
                ) : (
                  "R$ ••••••"
                )
              ) : (
                <span className="inline-block h-10 w-48 animate-pulse rounded-xl bg-ink-foreground/10" />
              )}
            </p>
            {conta.data && !ehPJ && (
              <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-marca">
                <Sparkles size={14} /> {fmtPontos(conta.data.pontos)} pontos
              </p>
            )}

            <div className="mt-7 flex gap-5 overflow-x-auto pb-1">
              <QuickAction icon={ArrowUpRight} label="Transferir" to="/transferir" />
              <QuickAction icon={Plus} label="Depositar" to="/depositar" />
              {ehPJ ? (
                <QuickAction icon={ListOrdered} label="Extrato" to="/extrato" />
              ) : (
                <>
                  <QuickAction icon={ShoppingBag} label="Loja" to="/loja" />
                  <QuickAction icon={Plane} label="Viagens" to="/viagens" />
                </>
              )}
            </div>
          </>
        )}
      </section>

      {ehPJ ? <PainelPJ /> : <VitrinePF />}

      <AtividadeRecente minha={conta.data?.carteira_id ?? 0} />
    </div>
  );
}

/** Vitrine "Para você" — só faz sentido para o consumidor (PF). */
function VitrinePF() {
  return (
    <section>
      <h2 className="mb-3 text-lg text-ink">Para você</h2>
      <div className="flex gap-4 overflow-x-auto pb-2">
        <PromoCard
          to="/loja"
          emoji="🛍️"
          eyebrow="Loja PayFlow"
          title="Compre e pague na hora"
          desc="Produtos de lojistas parceiros, direto do saldo."
        />
        <PromoCard
          to="/viagens"
          emoji="✈️"
          eyebrow="Viagens"
          title="Passagens com seus pontos"
          desc="Voe pagando em reais ou com pontos PayFlow."
        />
        <PromoCard
          to="/transferir"
          emoji="🧾"
          eyebrow="Reforma Tributária"
          title="Imposto certo no ato"
          desc="Pagou uma empresa? O CBS/IBS já sai separado."
        />
      </div>
    </section>
  );
}

/** Painel do lojista PJ — o diferencial: recebimentos com split automático. */
function PainelPJ() {
  const q = useQuery({ queryKey: ["vendas-pj"], queryFn: resumoVendasPJ });
  return (
    <section className="surface p-6 md:p-7">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-ink">Recebimentos com split</h2>
        <span className="rounded-full bg-tax-bg px-3 py-1 text-xs font-semibold text-tax2">
          automático
        </span>
      </div>
      {q.isError ? (
        <div className="mt-4">
          <ErrorBox>Não foi possível carregar as vendas.</ErrorBox>
        </div>
      ) : (
        <>
          <p className="mt-4 text-sm text-muted-foreground">Líquido recebido</p>
          <p className="tabular text-4xl font-semibold tracking-display text-pos">
            {q.data ? (
              fmtBRL(q.data.total_recebido_liquido)
            ) : (
              <span className="inline-block h-9 w-44 animate-pulse rounded-xl bg-tint" />
            )}
          </p>
          {q.data && (
            <>
              <div className="mt-5">
                <SplitBar
                  liquido={q.data.total_recebido_liquido}
                  imposto={q.data.total_imposto_retido}
                />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-[14px] bg-tint px-4 py-3">
                  <p className="text-mut3">Imposto retido</p>
                  <p className="tabular mt-0.5 font-semibold text-tax">
                    {fmtBRL(q.data.total_imposto_retido)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-tint px-4 py-3">
                  <p className="text-mut3">Vendas</p>
                  <p className="tabular mt-0.5 font-semibold text-ink">{q.data.qtd_vendas}</p>
                </div>
              </div>
              <p className="mt-4 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
                O CBS/IBS já chega separado. Você recebe só o líquido — sem apuração depois.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}

function AtividadeRecente({ minha }: { minha: number }) {
  const txs = useQuery({ queryKey: ["transacoes"], queryFn: transacoes });
  return (
    <section className="surface px-5 py-2 md:px-6">
      <div className="flex items-center justify-between pt-4">
        <h2 className="text-lg text-ink">Atividade recente</h2>
        <Link to="/extrato" className="text-sm font-medium text-mut2 hover:text-ink">
          Ver tudo
        </Link>
      </div>
      {txs.isLoading ? (
        <TxSkeleton n={4} />
      ) : txs.isError ? (
        <div className="py-4">
          <ErrorBox>Não foi possível carregar as transações.</ErrorBox>
        </div>
      ) : !txs.data?.length ? (
        <Empty title="Nada por aqui ainda" hint="Suas movimentações vão aparecer aqui." />
      ) : (
        <ul className="divide-y divide-border">
          {txs.data.slice(0, 5).map((t) => (
            <TxItem key={t.id} t={t} minha={minha} />
          ))}
        </ul>
      )}
    </section>
  );
}
