import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  Camera,
  FileText,
  Inbox,
  Plane,
  Receipt,
  RotateCcw,
  TrendingUp,
  ShoppingBag,
  Wallet,
  type LucideProps,
} from "lucide-react";
import { fmtBRL, fmtData, fmtId } from "@/lib/format";
import type { CategoriaTx, Produto, Transacao, Voo } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Logotipo Astro (arquivo oficial da marca; cor só preto ou branco, nunca colorido). */
export function Wordmark({
  size = "md",
  tone = "ink",
}: {
  size?: "sm" | "md" | "lg";
  tone?: "ink" | "light";
}) {
  const sizeClass = size === "lg" ? "h-7" : size === "sm" ? "h-[15px]" : "h-[18px]";
  return (
    <svg
      role="img"
      aria-label="Astro"
      viewBox="0 -61.28 353.76 62.56"
      fill={tone === "light" ? "#FFFFFF" : "#0A0A0A"}
      className={cn("inline-block w-auto shrink-0", sizeClass)}
    >
      <path d="M0 0 22.47 -60H36.33L58.8 0H44.31L29.4 -36.06L14.49 0Z" />
      <path d="M71.4 -19.6H86.68Q87.08 -16.88 89.16 -14.8Q91.24 -12.72 94.72 -11.6Q98.2 -10.48 102.84 -10.48Q109.48 -10.48 113.28 -12.32Q117.08 -14.16 117.08 -17.52Q117.08 -20.08 114.88 -21.48Q112.68 -22.88 106.68 -23.52L95.08 -24.72Q83 -25.92 77.6 -30.32Q72.2 -34.72 72.2 -42.32Q72.2 -48.32 75.76 -52.56Q79.32 -56.8 85.76 -59.04Q92.2 -61.28 100.84 -61.28Q109.4 -61.28 115.96 -58.8Q122.52 -56.32 126.44 -51.92Q130.36 -47.52 130.68 -41.6H115.4Q115.08 -44.08 113.2 -45.8Q111.32 -47.52 108.16 -48.52Q105 -49.52 100.6 -49.52Q94.52 -49.52 90.96 -47.8Q87.4 -46.08 87.4 -42.88Q87.4 -40.48 89.52 -39.12Q91.64 -37.76 97.08 -37.12L109.32 -35.76Q117.72 -34.88 122.76 -32.96Q127.8 -31.04 130.04 -27.68Q132.28 -24.32 132.28 -19.2Q132.28 -13.04 128.56 -8.44Q124.84 -3.84 118.16 -1.28Q111.48 1.28 102.6 1.28Q93.4 1.28 86.48 -1.36Q79.56 -4 75.6 -8.68Q71.64 -13.36 71.4 -19.6Z" />
      <path d="M165.72 -53.28H180.84V0H165.72ZM142.36 -60H204.2V-46.64H142.36Z" />
      <path d="M229.96 -33.6H252.44Q256.68 -33.6 259.16 -35.56Q261.64 -37.52 261.64 -41.04Q261.64 -44.56 259.16 -46.52Q256.68 -48.48 252.44 -48.48H227.8L234.6 -55.92V0H219.48V-60H254.44Q261.16 -60 266.2 -57.6Q271.24 -55.2 274.04 -50.96Q276.84 -46.72 276.84 -41.04Q276.84 -35.44 274.04 -31.2Q271.24 -26.96 266.2 -24.56Q261.16 -22.16 254.44 -22.16H229.96ZM239.64 -28.08H256.68L278.76 0H261.24Z" />
      <path d="M353.76 -30C353.76 -12.77 339.79 1.2 322.56 1.2C305.33 1.2 291.36 -12.77 291.36 -30C291.36 -47.23 305.33 -61.2 322.56 -61.2C330.92 -61.2 338.51 -57.91 344.12 -52.56C339.6 -56.48 333.7 -58.86 327.24 -58.86C313.02 -58.86 301.5 -47.34 301.5 -33.12C301.5 -18.9 313.02 -7.38 327.24 -7.38C341.46 -7.38 352.98 -18.9 352.98 -33.12C352.98 -35.96 352.52 -38.7 351.67 -41.26C353.02 -37.77 353.76 -33.97 353.76 -30Z" />
    </svg>
  );
}

export function SplitBar({ liquido, imposto }: { liquido: number; imposto: number }) {
  const total = liquido + imposto || 1;
  const pTax = (imposto / total) * 100;
  return (
    <div
      className="flex h-4 w-full gap-[2px]"
      role="img"
      aria-label={`Líquido ${fmtBRL(liquido)}, imposto ${fmtBRL(imposto)}`}
    >
      <div
        className="h-full rounded-full bg-ink transition-all duration-300"
        style={{ flexBasis: `${100 - pTax}%` }}
      />
      {imposto > 0 && (
        <div
          className="h-full min-w-1.5 rounded-full bg-ocre transition-all duration-300"
          style={{ flexBasis: `${pTax}%` }}
        />
      )}
    </div>
  );
}

export function ValueRow({
  label,
  value,
  tax,
  strong,
}: {
  label: string;
  value: number;
  tax?: boolean;
  strong?: boolean;
}) {
  return (
    <div
      className={cn("flex items-center justify-between py-2.5 text-[0.95rem]", tax && "text-tax")}
    >
      <span
        className={cn(
          tax ? "text-tax" : "text-muted-foreground",
          strong && "font-semibold text-ink",
        )}
      >
        {tax && <span className="mr-2 inline-block h-2 w-2 rounded-full bg-ocre align-middle" />}
        {label}
      </span>
      <span className={cn("tabular font-medium", strong && "text-lg font-semibold text-ink")}>
        {fmtBRL(value)}
      </span>
    </div>
  );
}

const ICONE_CAT: Record<CategoriaTx, ComponentType<LucideProps>> = {
  transferencia: ArrowUpRight,
  compra: ShoppingBag,
  viagem: Plane,
  deposito: ArrowDownLeft,
  recebimento: ArrowDownLeft,
  cobranca: FileText,
  rendimento: TrendingUp,
  estorno: RotateCcw,
};

export function TxItem({
  t,
  minha,
  clicavel = true,
}: {
  t: Transacao;
  minha: number;
  clicavel?: boolean;
}) {
  const entrada = t.destino_carteira_id === minha; // dinheiro entrando
  const Icon = ICONE_CAT[t.categoria] ?? ArrowUpRight;
  const imposto = t.cbs + t.ibs;
  // Para o lojista PJ, o que importa é o líquido recebido.
  const valor = entrada ? (t.aplicou_split ? t.liquido : t.valor_bruto) : t.valor_bruto;
  const corpo = (
    <>
      <div className="flex min-w-0 items-start gap-3">
        <div
          className={cn(
            "mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full",
            entrada
              ? "bg-[color-mix(in_oklab,var(--pos)_14%,transparent)] text-pos"
              : "bg-tint text-mut2",
          )}
        >
          <Icon size={18} />
        </div>
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">
            {t.descricao ||
              (entrada
                ? `De ${fmtId(t.origem_carteira_id)}`
                : `Para ${fmtId(t.destino_carteira_id)}`)}
          </p>
          <p className="text-sm text-mut3">{fmtData(t.criado_em)}</p>
          {entrada && t.status === "retida" && (
            <p className="mt-1 text-sm text-pending">
              <span className="rounded-full bg-tint px-2 py-0.5 text-xs font-semibold">retido</span>{" "}
              · Bloqueado por segurança
              {t.bloqueio_ate
                ? ` · libera até ${fmtData(t.bloqueio_ate)}`
                : " · liberação sem data informada"}
            </p>
          )}
          {t.aplicou_split && (
            <p className="mt-1 text-sm text-tax">
              {entrada
                ? `Imposto da nota ${fmtBRL(imposto)} retido no ato`
                : `Imposto da nota ${fmtBRL(imposto)} → Fisco`}
            </p>
          )}
        </div>
      </div>
      <span className={cn("tabular shrink-0 font-semibold", entrada ? "text-pos" : "text-ink")}>
        {entrada ? "+" : "−"} {fmtBRL(valor)}
      </span>
    </>
  );
  if (!clicavel) return <li className="flex items-start justify-between gap-4 py-4">{corpo}</li>;
  return (
    <li>
      <Link
        to="/comprovante/$id"
        params={{ id: String(t.id) }}
        className="-mx-2 flex items-start justify-between gap-4 rounded-[14px] px-2 py-4 transition hover:bg-tint/50"
      >
        {corpo}
      </Link>
    </li>
  );
}

export function TxSkeleton({ n = 4 }: { n?: number }) {
  return (
    <ul className="divide-y divide-border" aria-busy>
      {Array.from({ length: n }).map((_, i) => (
        <li key={i} className="flex items-center gap-3 py-4">
          <div className="h-10 w-10 animate-pulse rounded-full bg-tint" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-32 animate-pulse rounded-full bg-tint" />
            <div className="h-3 w-20 animate-pulse rounded-full bg-tint" />
          </div>
          <div className="h-4 w-20 animate-pulse rounded-full bg-tint" />
        </li>
      ))}
    </ul>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center py-12 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-tint text-mut2">
        <Inbox size={20} />
      </div>
      <p className="font-medium text-ink">{title}</p>
      {hint && <p className="mt-1 max-w-xs text-sm text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-[14px] bg-err-bg px-4 py-3 text-sm text-err"
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0" /> <span>{children}</span>
    </div>
  );
}

export function Field({
  label,
  id,
  children,
  hint,
}: {
  label: string;
  id: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium text-mut2">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-mut3">{hint}</p>}
    </div>
  );
}

export function SelfieCapture({
  value,
  onChange,
  title = "Selfie de cadastro",
}: {
  value: File | null;
  onChange: (f: File | null) => void;
  title?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => ref.current?.click()}
          className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-full bg-tint text-mut2 transition hover:bg-line2"
          aria-label={value ? "Trocar selfie" : "Capturar selfie"}
        >
          {url ? (
            <img src={url} alt="Selfie capturada" className="h-full w-full object-cover" />
          ) : (
            <Camera size={24} />
          )}
        </button>
        <div className="min-w-0">
          <p className="font-medium text-ink">{title}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Rosto de frente, sem óculos escuros, lugar iluminado, só você na foto.
          </p>
          <button
            type="button"
            onClick={() => ref.current?.click()}
            className="mt-2 text-sm font-semibold text-ink underline underline-offset-4"
          >
            {value ? "Trocar foto" : "Abrir câmera ou enviar foto"}
          </button>
        </div>
      </div>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        capture="user"
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          onChange(f);
          setUrl(f ? URL.createObjectURL(f) : null);
        }}
      />
    </div>
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-3xl text-ink md:text-4xl">{children}</h1>
      {sub && <p className="mt-1 text-muted-foreground">{sub}</p>}
    </div>
  );
}

// --- Componentes de banco ---------------------------------------------------

/** Ação circular estilo Mercado Pago/Inter (ícone + rótulo). Vira link ou botão. */
export function QuickAction({
  icon: Icon,
  label,
  to,
  onClick,
}: {
  icon: ComponentType<LucideProps>;
  label: string;
  to?: string;
  onClick?: () => void;
}) {
  const inner = (
    <>
      <span className="grid h-14 w-14 place-items-center rounded-full bg-[color-mix(in_oklab,var(--ink-fg)_14%,transparent)] text-ink-foreground transition group-hover:bg-[color-mix(in_oklab,var(--ink-fg)_22%,transparent)]">
        <Icon size={22} />
      </span>
      <span className="text-xs font-medium text-ink-foreground/90">{label}</span>
    </>
  );
  const klass = "group flex w-16 shrink-0 flex-col items-center gap-2 text-center";
  return to ? (
    <Link to={to} className={klass}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={klass}>
      {inner}
    </button>
  );
}

/** Atalho em card claro (grid de serviços do banco). */
export function Shortcut({
  icon: Icon,
  label,
  to,
  hint,
}: {
  icon: ComponentType<LucideProps>;
  label: string;
  to: string;
  hint?: string;
}) {
  return (
    <Link
      to={to}
      className="surface flex flex-col gap-2 p-4 transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-ink">
        <Icon size={20} />
      </span>
      <span className="mt-1 text-sm font-semibold text-ink">{label}</span>
      {hint && <span className="text-xs text-mut3">{hint}</span>}
    </Link>
  );
}

/** Card da vitrine "Para você" (carrossel horizontal). */
export function PromoCard({
  to,
  eyebrow,
  title,
  desc,
  emoji,
}: {
  to: string;
  eyebrow: string;
  title: string;
  desc: string;
  emoji: string;
}) {
  return (
    <Link
      to={to}
      className="relative w-72 shrink-0 overflow-hidden rounded-[20px] border border-border bg-gradient-to-br from-tint to-tax-bg p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <span className="text-3xl">{emoji}</span>
      <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-tax2">{eyebrow}</p>
      <p className="mt-1 text-lg font-semibold leading-tight text-ink">{title}</p>
      <p className="mt-1 text-sm text-mut2">{desc}</p>
    </Link>
  );
}

// --- Carrossel de banners (home PF, estilo PicPay) --------------------------

export interface Banner {
  id: string;
  eyebrow: string;
  title: string;
  desc: string;
  cta: string;
  to: string;
  emoji: string;
  /** Classes de gradiente do fundo do banner. */
  bg: string;
  /** true = texto claro sobre fundo escuro. */
  light?: boolean;
}

/** Banner rotativo com auto-play, dots e navegação por toque/clique. */
export function BannerCarousel({
  banners,
  interval = 4500,
}: {
  banners: Banner[];
  interval?: number;
}) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = banners.length;

  useEffect(() => {
    if (paused || n <= 1) return;
    const id = setInterval(() => setI((v) => (v + 1) % n), interval);
    return () => clearInterval(id);
  }, [paused, n, interval]);

  return (
    <section aria-label="Destaques" aria-roledescription="carrossel">
      <div
        className="relative overflow-hidden rounded-[22px]"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onTouchStart={() => setPaused(true)}
      >
        <div
          className="flex transition-transform duration-500 ease-out"
          style={{ transform: `translateX(-${i * 100}%)` }}
        >
          {banners.map((b) => (
            <Link
              key={b.id}
              to={b.to}
              className={cn(
                "relative flex min-w-full items-center gap-4 p-5 md:p-6",
                b.bg,
                b.light ? "text-ink-foreground" : "text-ink",
              )}
            >
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "text-[11px] font-semibold uppercase tracking-wide",
                    b.light ? "text-ink-foreground/70" : "text-tax2",
                  )}
                >
                  {b.eyebrow}
                </p>
                <p className="mt-1 text-lg font-semibold leading-tight md:text-xl">{b.title}</p>
                <p className={cn("mt-1 text-sm", b.light ? "text-ink-foreground/80" : "text-mut2")}>
                  {b.desc}
                </p>
                <span
                  className={cn(
                    "mt-3 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold",
                    b.light ? "bg-ink-foreground/15" : "bg-ink text-ink-foreground",
                  )}
                >
                  {b.cta} →
                </span>
              </div>
              <span className="shrink-0 text-5xl md:text-6xl" aria-hidden>
                {b.emoji}
              </span>
            </Link>
          ))}
        </div>
      </div>
      {n > 1 && (
        <div className="mt-3 flex justify-center gap-1.5">
          {banners.map((b, idx) => (
            <button
              key={b.id}
              aria-label={`Ir para o destaque ${idx + 1}`}
              onClick={() => setI(idx)}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                idx === i ? "w-6 bg-ink" : "w-1.5 bg-line2",
              )}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/** Bloco de métrica compacto (rótulo + valor), usado nos painéis. */
export function MetricTile({
  label,
  value,
  tone = "ink",
  hint,
}: {
  label: string;
  value: string;
  tone?: "ink" | "tax" | "pos";
  hint?: string;
}) {
  const color = tone === "tax" ? "text-tax" : tone === "pos" ? "text-pos" : "text-ink";
  return (
    <div className="rounded-[16px] bg-tint px-4 py-3">
      <p className="text-xs text-mut3">{label}</p>
      <p className={cn("tabular mt-0.5 text-lg font-semibold", color)}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-mut3">{hint}</p>}
    </div>
  );
}

export { Wallet, Receipt };
