import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  Camera,
  Inbox,
  Plane,
  Receipt,
  ShoppingBag,
  Wallet,
  type LucideProps,
} from "lucide-react";
import { fmtBRL, fmtData, fmtId } from "@/lib/format";
import type { CategoriaTx, Produto, Transacao, Voo } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Wordmark({
  size = "md",
  tone = "ink",
}: {
  size?: "sm" | "md" | "lg";
  tone?: "ink" | "light";
}) {
  const sizeClass = size === "lg" ? "text-4xl" : size === "sm" ? "text-[1.15rem]" : "text-[1.4rem]";
  return (
    <span
      aria-label="payflow"
      className={cn(
        "inline-flex items-baseline font-bold tracking-display",
        tone === "light" ? "text-ink-foreground" : "text-ink",
        sizeClass,
      )}
    >
      payfl
      <span
        aria-hidden
        className="mx-[0.04em] inline-block h-[0.56em] w-[0.56em] rounded-full bg-marca"
      />
      w
    </span>
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
};

export function TxItem({ t, minha }: { t: Transacao; minha: number }) {
  const entrada = t.destino_carteira_id === minha; // dinheiro entrando
  const Icon = ICONE_CAT[t.categoria] ?? ArrowUpRight;
  const imposto = t.cbs + t.ibs;
  // Para o lojista PJ, o que importa é o líquido recebido.
  const valor = entrada ? (t.aplicou_split ? t.liquido : t.valor_bruto) : t.valor_bruto;
  return (
    <li className="flex items-start justify-between gap-4 py-4">
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
          {t.aplicou_split && (
            <p className="mt-1 text-sm text-tax">
              {entrada
                ? `Imposto ${fmtBRL(imposto)} retido no ato`
                : `Imposto ${fmtBRL(imposto)} → Governo`}
            </p>
          )}
        </div>
      </div>
      <span className={cn("tabular shrink-0 font-semibold", entrada ? "text-pos" : "text-ink")}>
        {entrada ? "+" : "−"} {fmtBRL(valor)}
      </span>
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
export function BannerCarousel({ banners, interval = 4500 }: { banners: Banner[]; interval?: number }) {
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

export { Wallet, Receipt };
