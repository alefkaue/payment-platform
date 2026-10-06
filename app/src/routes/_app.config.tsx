import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ChevronRight,
  CreditCard,
  Fingerprint,
  Globe,
  LogOut,
  Moon,
  ShieldCheck,
  ShoppingCart,
  Snowflake,
  Users,
} from "lucide-react";
import { atualizarCartao, cvvDinamico, meuCartao, minhaConta } from "@/lib/api";
import { PORTES } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL } from "@/lib/format";
import type { Cartao } from "@/lib/types";
import { PageTitle } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/config")({
  head: () => ({ meta: [{ title: "Configurações — PayFlow" }] }),
  component: Config,
});

function Config() {
  const { conta: sessao, sair } = useAuth();
  const nav = useNavigate();
  const conta = useQuery({ queryKey: ["conta"], queryFn: minhaConta });
  const ehPJ = sessao?.tipo === "PJ";

  const lim = ehPJ
    ? { transacao: 250000, diario: 1000000, noturno: 50000 }
    : { transacao: 5000, diario: 10000, noturno: 1000 };

  const porte = conta.data?.porte ?? "GRANDE";
  const perfil = PORTES[porte];
  const metodoCert = ehPJ && perfil.metodo === "certificado";

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Cartão, limites, segurança e dados da sua conta.">Configurações</PageTitle>

      <CartaoSection />

      {/* Limites */}
      <section className="surface overflow-hidden">
        <h2 className="px-5 pt-5 text-lg text-ink">Limites</h2>
        <ul className="mt-2 divide-y divide-border">
          <LimiteRow label="Por transação (Pix/transferência)" valor={lim.transacao} />
          <LimiteRow label="Diário" valor={lim.diario} />
          <LimiteRow label="Noturno (20h–6h)" valor={lim.noturno} icon={<Moon size={15} />} />
        </ul>
      </section>

      {/* Segurança e acesso */}
      <section className="surface p-5">
        <h2 className="text-lg text-ink">Segurança e acesso</h2>
        <div className="mt-4 flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
            {metodoCert ? <ShieldCheck size={20} /> : <Fingerprint size={20} />}
          </span>
          <div className="min-w-0">
            <p className="font-medium text-ink">
              {metodoCert ? "Certificado digital e-CNPJ" : "Biometria do titular"}
            </p>
            <p className="text-xs text-mut3">
              {metodoCert
                ? "Acesso por ICP-Brasil (A1/A3) — o mesmo que assina a NF-e."
                : "Reconhecimento facial para entrar e aprovar pagamentos."}
            </p>
          </div>
        </div>
        {ehPJ && perfil.duplaAssinatura && (
          <div className="mt-3 flex items-center gap-3 rounded-[14px] bg-tint px-4 py-3">
            <Users size={18} className="shrink-0 text-ink" />
            <p className="text-sm text-mut2">
              <strong className="font-medium text-ink">3 assinantes com alçadas</strong> · dupla
              autorização (maker-checker) acima do limite.
            </p>
          </div>
        )}
      </section>

      {/* Dados da conta */}
      <section className="surface overflow-hidden">
        <h2 className="px-5 pt-5 text-lg text-ink">Conta</h2>
        <ul className="mt-2 divide-y divide-border px-5 pb-2 text-sm">
          <Dado label="Titular" valor={conta.data?.nome ?? "—"} />
          <Dado
            label={ehPJ ? "CNPJ" : "Tipo"}
            valor={ehPJ ? (conta.data?.cnpj ?? "—") : "Pessoa física"}
          />
          {ehPJ && <Dado label="Porte" valor={perfil.label} />}
        </ul>
      </section>

      <button
        onClick={() => {
          sair();
          nav({ to: "/login" });
        }}
        className="btn btn-ghost w-full gap-2 text-err"
      >
        <LogOut size={18} /> Sair da conta
      </button>
    </div>
  );
}

/* --- Cartão virtual (estado + segurança + CVV dinâmico) -------------------- */

function CartaoSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cartao"], queryFn: meuCartao });
  const mut = useMutation({
    mutationFn: atualizarCartao,
    onSuccess: (c) => qc.setQueryData(["cartao"], c),
  });
  const [cvv, setCvv] = useState<string | null>(null);

  const c = q.data;
  const congelado = c?.estado === "congelado";

  async function mostrarCvv() {
    const r = await cvvDinamico();
    setCvv(r.cvv);
    setTimeout(() => setCvv(null), 8000);
  }

  return (
    <section>
      <h2 className="mb-3 text-lg text-ink">{c?.apelido ?? "Cartão virtual"}</h2>

      <div
        className={cn(
          "relative overflow-hidden rounded-[20px] bg-ink p-5 text-ink-foreground shadow-lift transition",
          congelado && "opacity-60 saturate-0",
        )}
      >
        <div className="flex items-start justify-between">
          <span className="text-sm opacity-70">PayFlow</span>
          <CreditCard size={22} className="opacity-80" />
        </div>
        <p className="tabular mt-8 text-xl tracking-[0.18em]">
          {c?.numero_masc ?? "•••• •••• •••• ••••"}
        </p>
        <div className="mt-4 flex items-end justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-wide opacity-50">Validade</p>
            <p className="tabular text-sm font-medium">{c?.validade ?? "--/--"}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wide opacity-50">CVV dinâmico</p>
            <button
              onClick={mostrarCvv}
              className="tabular text-sm font-medium underline underline-offset-4 decoration-ink-foreground/40"
            >
              {cvv ?? "•••"}
            </button>
          </div>
          <span className="inline-flex h-6 w-10 items-center justify-center rounded bg-marca text-[10px] font-bold text-ink">
            {(c?.bandeira ?? "Visa").toUpperCase()}
          </span>
        </div>
        {congelado && (
          <span className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-ink-foreground/15 px-3 py-1 text-xs font-medium">
            Congelado
          </span>
        )}
      </div>

      <p className="mt-2 text-xs text-mut3">
        100% digital — sem plástico. Adicione à carteira do celular para pagar por aproximação.
      </p>

      <div className="surface mt-3 divide-y divide-border">
        <ToggleRow
          icon={<Snowflake size={16} />}
          label="Congelar cartão"
          hint="Bloqueia todas as compras na hora"
          on={congelado}
          busy={mut.isPending}
          onToggle={() => mut.mutate({ estado: congelado ? "ativo" : "congelado" })}
        />
        <ToggleRow
          icon={<ShoppingCart size={16} />}
          label="Compras online"
          on={!!c?.compras_online}
          busy={mut.isPending}
          disabled={congelado}
          onToggle={() => mut.mutate({ compras_online: !c?.compras_online })}
        />
        <ToggleRow
          icon={<Globe size={16} />}
          label="Compras internacionais"
          on={!!c?.compras_internacionais}
          busy={mut.isPending}
          disabled={congelado}
          onToggle={() => mut.mutate({ compras_internacionais: !c?.compras_internacionais })}
        />
        {c && (
          <div className="flex items-center justify-between px-4 py-3.5">
            <span className="text-sm text-mut2">Limite do cartão</span>
            <span className="tabular font-semibold text-ink">{fmtBRL(c.limite)}</span>
          </div>
        )}
      </div>
    </section>
  );
}

function ToggleRow({
  icon,
  label,
  hint,
  on,
  onToggle,
  busy,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  on: boolean;
  onToggle: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className={cn("flex items-center justify-between px-4 py-3.5", disabled && "opacity-50")}>
      <span className="flex items-center gap-2.5">
        <span className="text-mut2">{icon}</span>
        <span className="min-w-0">
          <span className="block text-sm text-ink">{label}</span>
          {hint && <span className="block text-[11px] text-mut3">{hint}</span>}
        </span>
      </span>
      <button
        role="switch"
        aria-checked={on}
        disabled={busy || disabled}
        onClick={onToggle}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed",
          on ? "bg-ink" : "bg-line2",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-background transition-all",
            on ? "left-[22px]" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

function LimiteRow({ label, valor, icon }: { label: string; valor: number; icon?: React.ReactNode }) {
  return (
    <li className="flex items-center justify-between px-5 py-3.5">
      <span className="flex items-center gap-2 text-sm text-mut2">
        {icon} {label}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="tabular font-semibold text-ink">{fmtBRL(valor)}</span>
        <ChevronRight size={16} className="text-mut3" />
      </span>
    </li>
  );
}

function Dado({ label, valor }: { label: string; valor: string }) {
  return (
    <li className="flex items-center justify-between py-2.5">
      <span className="text-mut3">{label}</span>
      <span className="font-medium text-ink">{valor}</span>
    </li>
  );
}
