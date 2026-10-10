import { useFecharAoVoltar } from "@/lib/mobile";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  CreditCard,
  Fingerprint,
  Globe,
  KeyRound,
  LogOut,
  Moon,
  ScanFace,
  ShieldCheck,
  ShoppingCart,
  Smartphone,
  Snowflake,
  Users,
} from "lucide-react";
import {
  alterarLimites,
  aparelhoAtual,
  atualizarCartao,
  confiarAparelho,
  criarChave,
  cvvDinamico,
  meuCartao,
  meusLimites,
  minhaConta,
  minhasChaves,
  MODO_API,
  trocarSenha,
} from "@/lib/api";
import { PAPEIS, PORTES, REGIMES_APURACAO } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData, parseValor } from "@/lib/format";
import type { Limites } from "@/lib/types";
import { ErrorBox, Field, PageTitle } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/config")({
  head: () => ({ meta: [{ title: "Configurações — Astro" }] }),
  component: Config,
});

function Config() {
  const { conta: sessao, sair } = useAuth();
  const nav = useNavigate();
  const conta = useQuery({ queryKey: ["conta", sessao?.numero], queryFn: minhaConta });
  const ehPJ = sessao?.tipo === "PJ";
  const perfil = PORTES[conta.data?.porte ?? "PME"];

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Cartão, limites, segurança e dados da sua conta.">Configurações</PageTitle>

      <CartaoSection />
      <LimitesSection podeEditar={!ehPJ || sessao?.papel === "admin"} />
      <AparelhoSection />
      <SenhaSection />

      {ehPJ && (
        <section className="surface p-5">
          <h2 className="text-lg text-ink">Seu acesso nesta empresa</h2>
          <div className="mt-4 flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
              <Users size={20} />
            </span>
            <div className="min-w-0">
              <p className="font-medium text-ink">{PAPEIS[sessao?.papel ?? "consulta"]}</p>
              <p className="text-xs text-mut3">
                {sessao?.alcada == null
                  ? "Sem limite de alçada."
                  : `Alçada de ${fmtBRL(sessao.alcada)} por operação. Acima disso, outra pessoa aprova.`}
              </p>
            </div>
          </div>
          <p className="mt-3 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
            {perfil.authDescricao}
          </p>
        </section>
      )}

      <section className="surface overflow-hidden">
        <h2 className="px-5 pt-5 text-lg text-ink">Conta</h2>
        <ul className="mt-2 divide-y divide-border px-5 pb-2 text-sm">
          <Dado label="Titular" valor={conta.data?.nome ?? "—"} />
          <Dado
            label="Agência / conta"
            valor={`${conta.data?.agencia ?? "0001"} / ${conta.data?.numero ?? "—"}`}
          />
          {ehPJ && <Dado label="CNPJ" valor={conta.data?.cnpj ?? "—"} />}
          {ehPJ && <Dado label="Porte" valor={perfil.label} />}
          {ehPJ && conta.data?.regime_apuracao && (
            <Dado label="Apuração" valor={REGIMES_APURACAO[conta.data.regime_apuracao].label} />
          )}
        </ul>
      </section>

      <ChavesSection ehPJ={ehPJ} />

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

/* --- Limites (no servidor; aumento com carência) --------------------------- */

type CampoLimite = "por_transacao" | "diurno" | "noturno";

function LimitesSection({ podeEditar }: { podeEditar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["limites"], queryFn: meusLimites });
  const [editando, setEditando] = useState<CampoLimite | null>(null);
  useFecharAoVoltar(editando, () => setEditando(null));
  const [valor, setValor] = useState("");
  const mut = useMutation({
    mutationFn: alterarLimites,
    onSuccess: (l: Limites) => {
      qc.setQueryData(["limites"], l);
      setEditando(null);
    },
  });
  const l = q.data;
  const linhas: { k: CampoLimite; label: string; icon?: React.ReactNode }[] = [
    { k: "por_transacao", label: "Por transação (Pix/transferência)" },
    { k: "diurno", label: "Diurno (6h–20h)" },
    { k: "noturno", label: "Noturno (20h–6h)", icon: <Moon size={15} /> },
  ];
  return (
    <section className="surface overflow-hidden">
      <h2 className="px-5 pt-5 text-lg text-ink">Limites</h2>
      <p className="px-5 text-xs text-mut3">
        Reduzir vale na hora. Aumentar só vale 24h depois: se alguém tentar subir seu limite num
        golpe, dá tempo de perceber.
      </p>
      <ul className="mt-2 divide-y divide-border">
        {linhas.map(({ k, label, icon }) => {
          const pendente = l?.pendente?.[k];
          return (
            <li key={k} className="px-5 py-3.5">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-sm text-mut2">
                  {icon} {label}
                </span>
                {editando === k ? (
                  <form
                    className="flex items-center gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const v = parseValor(valor);
                      if (v > 0) mut.mutate({ [k]: v });
                    }}
                  >
                    <input
                      autoComplete="off"
                      autoFocus
                      inputMode="decimal"
                      aria-label={`Novo limite: ${label}`}
                      className="field h-9 w-28 tabular"
                      value={valor}
                      onChange={(e) => setValor(e.target.value)}
                    />
                    <button className="btn btn-ink h-9 px-3 text-sm" disabled={mut.isPending}>
                      Salvar
                    </button>
                  </form>
                ) : (
                  <button
                    className="tabular font-semibold text-ink disabled:cursor-default"
                    disabled={!podeEditar || !l}
                    onClick={() => {
                      setEditando(k);
                      setValor(l ? String(l[k]) : "");
                    }}
                  >
                    {l ? fmtBRL(l[k]) : "—"}
                  </button>
                )}
              </div>
              {pendente != null && l?.pendente && (
                <p className="mt-1 text-xs text-tax2">
                  Aumento para {fmtBRL(pendente)} vale a partir de {fmtData(l.pendente.vigente_em)}.
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {mut.isError && (
        <div className="px-5 pb-4">
          <ErrorBox>{(mut.error as Error).message}</ErrorBox>
        </div>
      )}
    </section>
  );
}

/* --- Aparelho confiável --------------------------------------------------- */

function AparelhoSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["aparelho"], queryFn: aparelhoAtual });
  const [liveness, setLiveness] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const confiavel = q.data?.confiavel ?? true;
  return (
    <section className="surface p-5">
      <h2 className="text-lg text-ink">Segurança e acesso</h2>
      <div className="mt-4 flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
          <Fingerprint size={20} />
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">Biometria da pessoa</p>
          <p className="text-xs text-mut3">
            Reconhecimento facial para entrar e aprovar pagamentos. Na empresa, cada usuário entra
            com o próprio rosto; o papel e a alçada definem o que pode fazer.
          </p>
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
          {confiavel ? <ShieldCheck size={20} /> : <Smartphone size={20} />}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">
            {confiavel ? "Este aparelho é confiável" : "Aparelho ainda não confirmado"}
          </p>
          <p className="text-xs text-mut3">
            {confiavel
              ? "Verificação facial pedida em pagamentos acima de R$ 500."
              : "Limite de R$ 200 por Pix e R$ 1.000 por dia até confirmar com o rosto."}
          </p>
        </div>
      </div>
      {!confiavel && (
        <button className="btn btn-ink mt-4 w-full gap-2" onClick={() => setLiveness(true)}>
          <ScanFace size={18} /> Confirmar este aparelho
        </button>
      )}
      <Link to="/seguranca" className="btn btn-ghost mt-4 w-full gap-2">
        <Smartphone size={18} /> Aparelhos, sessões e atividade
      </Link>
      {erro && (
        <div className="mt-3">
          <ErrorBox>{erro}</ErrorBox>
        </div>
      )}
      {liveness && (
        <LivenessCheck
          onClose={() => setLiveness(false)}
          onSuccess={async (prova) => {
            await confiarAparelho(prova);
            setLiveness(false);
            void qc.invalidateQueries({ queryKey: ["aparelho"] });
          }}
        />
      )}
    </section>
  );
}

/* --- Senha ---------------------------------------------------------------- */

function SenhaSection() {
  const [aberto, setAberto] = useState(false);
  useFecharAoVoltar(aberto, () => {
    setAberto(false);
    setAtual("");
    setNova("");
    setRepetida("");
  });
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [liveness, setLiveness] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  function pedirRosto(e: React.FormEvent) {
    e.preventDefault();
    if (!atual || !nova) return setErro("Preencha a senha atual e a nova.");
    if (nova.length < 10) return setErro("A senha nova precisa ter ao menos 10 caracteres.");
    if (nova !== repetida) return setErro("As duas senhas novas não são iguais.");
    setErro(null);
    setLiveness(true);
  }

  function fechar() {
    setAberto(false);
    setAtual("");
    setNova("");
    setRepetida("");
    setErro(null);
  }

  return (
    <section className="surface p-5">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
          <KeyRound size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">Senha</p>
          <p className="text-xs text-mut3">
            Para trocar, informe a senha atual e confirme com o seu rosto. Os outros aparelhos saem
            da conta.
          </p>
        </div>
      </div>
      {ok && !aberto && <p className="mt-3 text-sm text-pos">{ok}</p>}
      {aberto ? (
        <form onSubmit={pedirRosto} className="mt-4 space-y-4">
          <Field label="Senha atual" id="senha-atual">
            <input
              id="senha-atual"
              type="password"
              autoComplete="current-password"
              className="field"
              value={atual}
              onChange={(e) => setAtual(e.target.value)}
            />
          </Field>
          <Field label="Senha nova" id="senha-nova" hint="Ao menos 10 caracteres.">
            <input
              id="senha-nova"
              type="password"
              autoComplete="new-password"
              className="field"
              value={nova}
              onChange={(e) => setNova(e.target.value)}
            />
          </Field>
          <Field label="Repita a senha nova" id="senha-repetida">
            <input
              id="senha-repetida"
              type="password"
              autoComplete="new-password"
              className="field"
              value={repetida}
              onChange={(e) => setRepetida(e.target.value)}
            />
          </Field>
          {erro && <ErrorBox>{erro}</ErrorBox>}
          <button className="btn btn-ink w-full gap-2" disabled={enviando}>
            <ScanFace size={18} /> {enviando ? "Trocando…" : "Confirmar com o rosto"}
          </button>
          <button type="button" className="btn btn-ghost w-full" onClick={fechar}>
            Cancelar
          </button>
        </form>
      ) : (
        <button
          className="btn btn-ghost mt-4 w-full"
          onClick={() => {
            setOk(null);
            setAberto(true);
          }}
        >
          Trocar senha
        </button>
      )}
      {liveness && (
        <LivenessCheck
          onClose={() => setLiveness(false)}
          onSuccess={async (prova) => {
            setEnviando(true);
            await trocarSenha(atual, nova, prova)
              .then((n) => {
                setLiveness(false);
                fechar();
                setOk(
                  n > 0
                    ? `Senha alterada. ${n} ${n === 1 ? "outra sessão foi encerrada" : "outras sessões foram encerradas"}.`
                    : "Senha alterada.",
                );
              })
              .finally(() => setEnviando(false));
          }}
        />
      )}
    </section>
  );
}

/* --- Chaves Pix ----------------------------------------------------------- */

function ChavesSection({ ehPJ }: { ehPJ: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["chaves"], queryFn: minhasChaves });
  const mut = useMutation({
    mutationFn: (tipo: string) => criarChave(tipo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chaves"] }),
  });
  const tipoDoc = ehPJ ? "cnpj" : "cpf";
  const temDoc = q.data?.some((k) => k.tipo === tipoDoc);
  return (
    <section className="surface p-5">
      <h2 className="flex items-center gap-2 text-lg text-ink">
        <KeyRound size={18} /> Chaves Pix
      </h2>
      {q.data?.length ? (
        <ul className="mt-3 divide-y divide-border text-sm">
          {q.data.map((k) => (
            <li key={k.id} className="flex items-center justify-between gap-3 py-2.5">
              <span className="uppercase text-mut3">{k.tipo}</span>
              <span className="truncate font-mono text-xs text-ink">{k.valor}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-mut3">
          Você ainda não tem chaves. Crie uma para receber Pix.
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {!temDoc && (
          <button
            className="btn btn-ghost h-9 text-sm"
            disabled={mut.isPending}
            onClick={() => mut.mutate(tipoDoc)}
          >
            Usar meu {ehPJ ? "CNPJ" : "CPF"}
          </button>
        )}
        <button
          className="btn btn-ghost h-9 text-sm"
          disabled={mut.isPending}
          onClick={() => mut.mutate("aleatoria")}
        >
          Criar chave aleatória
        </button>
      </div>
      {mut.isError && (
        <div className="mt-3">
          <ErrorBox>{(mut.error as Error).message}</ErrorBox>
        </div>
      )}
    </section>
  );
}

/* --- Cartão virtual (estado + segurança + CVV dinâmico) -------------------- */

export function CartaoSection() {
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
          <span className="text-sm opacity-70">Astro</span>
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
        {MODO_API && " Cartão em demonstração: a emissão real ainda não está ligada ao banco."}
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

function Dado({ label, valor }: { label: string; valor: string }) {
  return (
    <li className="flex items-center justify-between py-2.5">
      <span className="text-mut3">{label}</span>
      <span className="font-medium text-ink">{valor}</span>
    </li>
  );
}
