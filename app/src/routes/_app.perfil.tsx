import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ChevronRight, LogOut, Settings, ShieldCheck, Smartphone } from "lucide-react";
import { aparelhoAtual, minhaConta } from "@/lib/api";
import { PAPEIS, PORTES, REGIMES_APURACAO } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, iniciais } from "@/lib/format";
import { PageTitle } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/perfil")({
  head: () => ({ meta: [{ title: "Meu perfil — Astro" }] }),
  component: Perfil,
});

function Perfil() {
  const { conta: sessao, sair } = useAuth();
  const nav = useNavigate();
  const conta = useQuery({ queryKey: ["conta", sessao?.numero], queryFn: minhaConta });
  const aparelho = useQuery({ queryKey: ["aparelho"], queryFn: aparelhoAtual });
  const ehPJ = sessao?.tipo === "PJ";
  const c = conta.data;
  const confiavel = aparelho.data?.confiavel ?? true;

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Seus dados, verificação e dispositivos.">Meu perfil</PageTitle>

      {/* Cabeçalho do perfil */}
      <section className="surface flex items-center gap-4 p-6">
        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-ink text-xl font-semibold text-ink-foreground">
          {iniciais(c?.nome)}
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold text-ink">{c?.nome ?? "…"}</h2>
          <p className="truncate text-sm text-mut2">
            {ehPJ ? "Conta empresa (PJ)" : "Conta pessoa física"}
          </p>
          <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-[color-mix(in_oklab,var(--pos)_14%,transparent)] px-2.5 py-0.5 text-xs font-medium text-pos">
            <BadgeCheck size={13} /> Identidade verificada
          </span>
        </div>
      </section>

      {/* Dados */}
      <section className="surface overflow-hidden">
        <h2 className="px-5 pt-5 text-lg text-ink">Dados cadastrais</h2>
        <ul className="mt-2 divide-y divide-border px-5 pb-2 text-sm">
          <Dado label={ehPJ ? "Razão social" : "Nome completo"} valor={c?.nome ?? "—"} />
          {ehPJ ? (
            <>
              <Dado label="CNPJ" valor={c?.cnpj ?? "—"} />
              <Dado label="Setor" valor={c?.setor ?? "—"} />
              <Dado label="Porte" valor={c?.porte ? PORTES[c.porte].label : "—"} />
              {c?.regime_apuracao && (
                <Dado label="Apuração" valor={REGIMES_APURACAO[c.regime_apuracao].label} />
              )}
              <Dado label="Seu papel" valor={PAPEIS[sessao?.papel ?? "consulta"]} />
              <Dado
                label="Sua alçada"
                valor={sessao?.alcada == null ? "Sem limite" : fmtBRL(sessao.alcada)}
              />
            </>
          ) : (
            <>
              <Dado label="CPF" valor="•••.•••.789-00" />
              <Dado label="E-mail" valor="marina@email.com" />
              <Dado label="Celular" valor="(11) 9 ••••-4521" />
            </>
          )}
          <Dado label="Agência / conta" valor={`${c?.agencia ?? "0001"} / ${c?.numero ?? "—"}`} />
        </ul>
      </section>

      {/* Segurança do aparelho */}
      <section className="surface p-5">
        <h2 className="text-lg text-ink">Este aparelho</h2>
        <div className="mt-3 flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
            {confiavel ? <ShieldCheck size={20} /> : <Smartphone size={20} />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-ink">
              {confiavel ? "Aparelho confiável" : "Aparelho não confirmado"}
            </p>
            <p className="text-xs text-mut3">
              {confiavel
                ? "Verificação facial pedida em pagamentos acima de R$ 500."
                : "Confirme com o rosto para liberar limites maiores."}
            </p>
          </div>
          <Link to="/config" className="text-mut3 hover:text-ink" aria-label="Gerenciar segurança">
            <ChevronRight size={20} />
          </Link>
        </div>
      </section>

      {/* Atalhos */}
      <section className="surface overflow-hidden">
        <LinhaLink to="/config" icon={<Settings size={18} />} label="Configurações da conta" />
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

function Dado({ label, valor }: { label: string; valor: string }) {
  return (
    <li className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-mut3">{label}</span>
      <span className="truncate font-medium text-ink">{valor}</span>
    </li>
  );
}

function LinhaLink({ to, icon, label }: { to: "/config"; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 px-5 py-4 transition hover:bg-tint">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-tint text-ink">{icon}</span>
      <span className="flex-1 font-medium text-ink">{label}</span>
      <ChevronRight size={18} className="text-mut3" />
    </Link>
  );
}
