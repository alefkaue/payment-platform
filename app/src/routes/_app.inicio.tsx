import { createFileRoute, Link } from "@tanstack/react-router";
import { Settings, TrendingUp } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowUpRight,
  Building2,
  Coins,
  Eye,
  EyeOff,
  FileText,
  Landmark,
  ListOrdered,
  Plane,
  Plus,
  QrCode,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Users,
} from "lucide-react";
import { apuracaoPJ, listarFaturas, minhaConta, transacoes } from "@/lib/api";
import { PORTES } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData, fmtPontos, iniciais, primeiroNome } from "@/lib/format";
import type { Conta, Fatura } from "@/lib/types";
import {
  type Banner,
  BannerCarousel,
  Empty,
  ErrorBox,
  MetricTile,
  QuickAction,
  Shortcut,
  SplitBar,
  TxItem,
  TxSkeleton,
} from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/inicio")({
  head: () => ({
    meta: [
      { title: "Início — PayFlow" },
      { name: "description", content: "Sua conta PayFlow." },
    ],
  }),
  component: Inicio,
});

function Inicio() {
  const { conta: sessaoConta } = useAuth();
  const conta = useQuery({ queryKey: ["conta"], queryFn: minhaConta });
  const ehPJ = sessaoConta?.tipo === "PJ";

  return (
    <div className="enter space-y-7">
      <header className="flex items-center gap-3">
        <span
          aria-hidden
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-sm font-semibold text-ink-foreground"
        >
          {iniciais(conta.data?.nome)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">Olá,</p>
          <h1 className="truncate text-lg font-semibold leading-tight text-ink">
            {primeiroNome(conta.data?.nome) ?? "…"}
          </h1>
          {ehPJ && conta.data?.porte && (
            <p className="mt-0.5 flex items-center gap-1 text-[11px] text-mut3">
              <Building2 size={12} className="shrink-0" />
              <span className="truncate">
                {conta.data.setor} · {PORTES[conta.data.porte].label}
              </span>
            </p>
          )}
        </div>
        <Link
          to="/config"
          aria-label="Configurações"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line2 text-mut2 transition hover:bg-tint hover:text-ink md:hidden"
        >
          <Settings size={18} />
        </Link>
      </header>

      {ehPJ ? <InicioPJ /> : <InicioPF />}
    </div>
  );
}

/* ========================================================================== */
/*  PESSOA FÍSICA — experiência de consumidor (estilo PicPay)                  */
/* ========================================================================== */

const BANNERS_PF: Banner[] = [
  {
    id: "rende",
    eyebrow: "Dinheiro parado rende",
    title: "Seu saldo rende 100% do CDI",
    desc: "Sem aplicar nada: o dinheiro na conta rende sozinho, todo dia.",
    cta: "Criar uma caixinha",
    to: "/depositar",
    emoji: "📈",
    bg: "bg-ink",
    light: true,
  },
  {
    id: "pontos",
    eyebrow: "Viagens",
    title: "Seus pontos viram passagem",
    desc: "Voe pagando em reais ou com pontos PayFlow.",
    cta: "Ver voos",
    to: "/viagens",
    emoji: "✈️",
    bg: "bg-gradient-to-br from-marca to-ocre",
  },
  {
    id: "loja",
    eyebrow: "Loja PayFlow",
    title: "Compre e pague na hora",
    desc: "Produtos de lojistas parceiros, direto do saldo.",
    cta: "Explorar loja",
    to: "/loja",
    emoji: "🛍️",
    bg: "bg-gradient-to-br from-tint to-tax-bg",
  },
  {
    id: "pix",
    eyebrow: "Pix",
    title: "Transfira de graça, na hora",
    desc: "Pix 24h sem tarifa para qualquer banco.",
    cta: "Fazer um Pix",
    to: "/transferir",
    emoji: "💸",
    bg: "bg-ink",
    light: true,
  },
];

function InicioPF() {
  const conta = useQuery({ queryKey: ["conta"], queryFn: minhaConta });
  const [ver, setVer] = useState(true);

  return (
    <>
      {/* Cartão de saldo (estilo neobanco) */}
      <section className="rounded-[22px] bg-ink p-6 text-ink-foreground shadow-lift" aria-label="Saldo">
        <div className="flex items-center justify-between">
          <p className="text-sm opacity-60">Saldo disponível</p>
          <button
            onClick={() => setVer((v) => !v)}
            aria-label={ver ? "Ocultar saldo" : "Mostrar saldo"}
            className="text-ink-foreground/70 hover:text-ink-foreground"
          >
            {ver ? <Eye size={18} /> : <EyeOff size={18} />}
          </button>
        </div>
        <p className="tabular mt-2 text-[2.4rem] font-semibold leading-none tracking-display">
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
        {conta.data && (
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="inline-flex items-center gap-1.5 text-marca">
              <Sparkles size={14} /> {fmtPontos(conta.data.pontos)} pontos
            </span>
            <span className="inline-flex items-center gap-1.5 text-pos">
              <TrendingUp size={14} /> Rende 100% do CDI
            </span>
          </div>
        )}
        <div className="mt-6 flex justify-between">
          <QuickAction icon={ArrowUpRight} label="Transferir" to="/transferir" />
          <QuickAction icon={Plus} label="Depositar" to="/depositar" />
          <QuickAction icon={ShoppingBag} label="Loja" to="/loja" />
          <QuickAction icon={Plane} label="Viagens" to="/viagens" />
        </div>
      </section>

      <BannerCarousel banners={BANNERS_PF} />

      {/* Pro dia a dia — grade de serviços */}
      <section>
        <h2 className="mb-3 text-lg text-ink">Pro dia a dia</h2>
        <div className="grid grid-cols-3 gap-3">
          <Shortcut icon={QrCode} label="Pix" to="/transferir" />
          <Shortcut icon={Plus} label="Depositar" to="/depositar" />
          <Shortcut icon={ShoppingBag} label="Loja" to="/loja" />
          <Shortcut icon={Plane} label="Viagens" to="/viagens" />
          <Shortcut icon={Sparkles} label="Pontos" to="/viagens" />
          <Shortcut icon={ListOrdered} label="Extrato" to="/extrato" />
        </div>
      </section>

      <AtividadeRecente minha={conta.data?.carteira_id ?? 0} titulo="Atividade recente" />
    </>
  );
}

/* ========================================================================== */
/*  EMPRESA (PJ) — centro financeiro-fiscal da indústria                       */
/* ========================================================================== */

function InicioPJ() {
  const conta = useQuery({ queryKey: ["conta"], queryFn: minhaConta });
  const [ver, setVer] = useState(true);

  return (
    <>
      {/* Caixa da empresa */}
      <section className="rounded-[22px] bg-ink p-6 text-ink-foreground shadow-lift" aria-label="Saldo">
        <div className="flex items-center justify-between">
          <p className="text-sm opacity-60">Saldo em conta</p>
          <button
            onClick={() => setVer((v) => !v)}
            aria-label={ver ? "Ocultar saldo" : "Mostrar saldo"}
            className="text-ink-foreground/70 hover:text-ink-foreground"
          >
            {ver ? <Eye size={18} /> : <EyeOff size={18} />}
          </button>
        </div>
        <p className="tabular mt-2 text-[2.2rem] font-semibold leading-none tracking-display">
          {conta.data ? (
            ver ? (
              fmtBRL(conta.data.saldo)
            ) : (
              "R$ ••••••"
            )
          ) : (
            <span className="inline-block h-9 w-48 animate-pulse rounded-xl bg-ink-foreground/10" />
          )}
        </p>
        <div className="mt-6 flex justify-between">
          <QuickAction icon={ArrowUpRight} label="Pagar" to="/transferir" />
          <QuickAction icon={Plus} label="Depositar" to="/depositar" />
          <QuickAction icon={FileText} label="Contas" to="/contas" />
          <QuickAction icon={ListOrdered} label="Extrato" to="/extrato" />
        </div>
      </section>

      <ApuracaoCard />
      <CreditosCard creditos={conta.data?.creditos ?? 0} />
      <ContasPreview />
      <AcessoCard conta={conta.data} />
      <AtividadeRecente minha={conta.data?.carteira_id ?? 0} titulo="Movimentações recentes" />
    </>
  );
}

/** O herói do pitch B2B: apuração automática com split inteligente. */
function ApuracaoCard() {
  const q = useQuery({ queryKey: ["apuracao-pj"], queryFn: apuracaoPJ });

  return (
    <section className="surface overflow-hidden p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg text-ink">Apuração automática</h2>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-tax-bg px-3 py-1 text-xs font-semibold text-tax2">
          <ShieldCheck size={13} /> no ato
        </span>
      </div>

      {q.isError ? (
        <div className="mt-4">
          <ErrorBox>Não foi possível carregar a apuração.</ErrorBox>
        </div>
      ) : !q.data ? (
        <div className="mt-4 h-28 animate-pulse rounded-2xl bg-tint" />
      ) : (
        <>
          <p className="mt-1 text-sm text-muted-foreground">
            {q.data.periodo} · regime {q.data.regime} ({q.data.aliquota_pct.toLocaleString("pt-BR")}
            %)
          </p>

          <p className="mt-4 text-sm text-mut2">Imposto recolhido ao Fisco</p>
          <p className="tabular text-4xl font-semibold tracking-display text-ink">
            {fmtBRL(q.data.imposto_recolhido)}
          </p>
          <p className="mt-1 text-sm text-pos">
            de {fmtBRL(q.data.imposto_devido)} devidos — o resto foi abatido pelos seus créditos.
          </p>

          {/* devido = crédito usado + recolhido */}
          <div className="mt-5">
            <SplitBar liquido={q.data.credito_usado} imposto={q.data.imposto_recolhido} />
            <div className="mt-2 flex justify-between text-xs">
              <span className="text-pos">
                Crédito abatido {fmtBRL(q.data.credito_usado)}
              </span>
              <span className="text-tax">Recolhido {fmtBRL(q.data.imposto_recolhido)}</span>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <MetricTile label="Faturamento no mês" value={fmtBRL(q.data.faturamento)} />
            <MetricTile label="Imposto devido" value={fmtBRL(q.data.imposto_devido)} tone="tax" />
          </div>

          <p className="mt-4 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
            <strong className="font-semibold">Zero apuração manual.</strong> O IBS/CBS é calculado e
            separado em cada venda — sem fechamento mensal, sem contador apurando depois.
          </p>
        </>
      )}
    </section>
  );
}

/** Créditos tributários acumulados + caixa preservado (pilar fluxo de caixa). */
function CreditosCard({ creditos }: { creditos: number }) {
  const q = useQuery({ queryKey: ["apuracao-pj"], queryFn: apuracaoPJ });
  return (
    <section className="grid gap-3 sm:grid-cols-2">
      <div className="surface flex flex-col p-5">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-ink">
          <Coins size={20} />
        </span>
        <p className="mt-3 text-sm text-mut2">Créditos de IBS/CBS</p>
        <p className="tabular text-2xl font-semibold tracking-display text-ink">{fmtBRL(creditos)}</p>
        <p className="mt-1 text-xs text-mut3">
          Acumulados nas compras de insumo, energia e máquinas. Abatem seu imposto automaticamente.
        </p>
      </div>
      <div className="surface flex flex-col p-5">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-pos">
          <Landmark size={20} />
        </span>
        <p className="mt-3 text-sm text-mut2">Caixa preservado no mês</p>
        <p className="tabular text-2xl font-semibold tracking-display text-pos">
          {q.data ? fmtBRL(q.data.caixa_preservado) : "—"}
        </p>
        <p className="mt-1 text-xs text-mut3">
          Valor de imposto que nunca passou pelo seu caixa — você não precisa provisionar.
        </p>
      </div>
    </section>
  );
}

/** Acesso & assinaturas — verificação por certificado e-CNPJ, alçadas, dupla autorização. */
function AcessoCard({ conta }: { conta: Conta | undefined }) {
  const porte = conta?.porte ?? "GRANDE";
  const perfil = PORTES[porte];
  const cert = perfil.metodo === "certificado";
  return (
    <section className="surface p-6">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
          <ShieldCheck size={20} />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg text-ink">Acesso & assinaturas</h2>
          <p className="text-xs text-mut3">
            {cert ? "Certificado digital e-CNPJ (ICP-Brasil)" : "Biometria do titular (MEI)"}
          </p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <MetricTile
          label="Assinantes"
          value={perfil.duplaAssinatura ? "3 com alçadas" : "Titular"}
        />
        <MetricTile
          label="Autorização"
          value={perfil.duplaAssinatura ? "Dupla (maker-checker)" : "Simples"}
        />
      </div>
      {perfil.duplaAssinatura && (
        <p className="mt-4 flex items-start gap-2 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
          <Users size={18} className="mt-0.5 shrink-0" />
          Pagamentos acima da alçada exigem um segundo aprovador — sem selfie, com assinatura por
          certificado.
        </p>
      )}
    </section>
  );
}

/** Prévia das contas a receber / a pagar (B2B). */
function ContasPreview() {
  const q = useQuery({ queryKey: ["faturas"], queryFn: () => listarFaturas() });
  return (
    <section className="surface px-5 py-2">
      <div className="flex items-center justify-between pt-4">
        <h2 className="text-lg text-ink">Contas a pagar e receber</h2>
        <Link to="/contas" className="text-sm font-medium text-mut2 hover:text-ink">
          Ver tudo
        </Link>
      </div>
      {q.isLoading ? (
        <div className="space-y-3 py-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-tint" />
          ))}
        </div>
      ) : q.isError ? (
        <div className="py-4">
          <ErrorBox>Não foi possível carregar as contas.</ErrorBox>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {q.data?.slice(0, 3).map((f) => (
            <FaturaRow key={f.id} f={f} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function FaturaRow({ f }: { f: Fatura }) {
  const receber = f.direcao === "receber";
  return (
    <li className="flex items-center justify-between gap-4 py-3.5">
      <div className="flex min-w-0 items-center gap-3">
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${
            receber
              ? "bg-[color-mix(in_oklab,var(--pos)_14%,transparent)] text-pos"
              : "bg-tint text-mut2"
          }`}
        >
          {receber ? <ArrowUpRight size={18} /> : <ArrowUpRight size={18} className="rotate-90" />}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{f.contraparte}</p>
          <p className="truncate text-xs text-mut3">
            {f.nf} · vence {fmtData(f.vencimento).split(",")[0]}
          </p>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <p className={`tabular font-semibold ${receber ? "text-pos" : "text-ink"}`}>
          {receber ? "+" : "−"} {fmtBRL(receber ? f.liquido : f.valor_bruto)}
        </p>
        <p className="text-[11px] text-mut3">
          {receber ? `imposto ${fmtBRL(f.imposto)}` : `+${fmtBRL(f.credito_gerado)} crédito`}
        </p>
      </div>
    </li>
  );
}

/* ========================================================================== */

function AtividadeRecente({ minha, titulo }: { minha: number; titulo: string }) {
  const txs = useQuery({ queryKey: ["transacoes"], queryFn: transacoes });
  return (
    <section className="surface px-5 py-2">
      <div className="flex items-center justify-between pt-4">
        <h2 className="text-lg text-ink">{titulo}</h2>
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
