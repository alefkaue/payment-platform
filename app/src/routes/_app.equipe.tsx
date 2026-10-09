import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, ShieldCheck, UserPlus } from "lucide-react";
import {
  convidarMembro,
  equipe,
  MODO_API,
  mudarAcessoMembro,
  politicaEmpresa,
  type AcaoMembro,
} from "@/lib/api";
import { PAPEIS } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData, iniciais, maskDoc, parseValor } from "@/lib/format";
import type {
  ConvidarPayload,
  MembroEquipe,
  PapelVinculo,
  ProvaBiometrica,
  StatusVinculo,
} from "@/lib/types";
import { Empty, ErrorBox, Field, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/equipe")({
  head: () => ({ meta: [{ title: "Equipe & alçadas — Astro" }] }),
  component: Equipe,
});

const CORES_PAPEL: Record<PapelVinculo, string> = {
  admin: "bg-ink text-ink-foreground",
  aprovador: "bg-tax-bg text-tax2",
  operador: "bg-tint text-ink",
  consulta: "bg-tint text-mut2",
};

const STATUS: Record<StatusVinculo, { rotulo: string; cor: string } | null> = {
  ativo: null,
  pendente: { rotulo: "convite enviado", cor: "text-pending" },
  aguardando: { rotulo: "aguardando outro admin", cor: "text-pending" },
  suspenso: { rotulo: "suspenso", cor: "text-err" },
  revogado: { rotulo: "acesso encerrado", cor: "text-mut3" },
};

/**
 * Quem acessa a conta da empresa. Cada pessoa tem o próprio login (nunca uma
 * conta compartilhada): o admin convida pelo CPF e ela aceita com o próprio
 * rosto. O que pode ser concedido depende do porte (MEI, PME, Grande).
 */
function Equipe() {
  const { conta } = useAuth();
  const [nova, setNova] = useState(false);
  const q = useQuery({ queryKey: ["equipe", conta?.numero], queryFn: equipe });
  const pol = useQuery({ queryKey: ["politica", conta?.numero], queryFn: politicaEmpresa });

  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;
  const souAdmin = conta?.papel === "admin";
  const ativos = q.data?.filter((m) => m.status !== "revogado") ?? [];
  const encerrados = q.data?.filter((m) => m.status === "revogado") ?? [];

  return (
    <div className="enter">
      <PageTitle sub="Cada pessoa entra com o próprio login e rosto. O papel e a alçada definem o que ela pode fazer.">
        Equipe & alçadas
      </PageTitle>

      {pol.data && (
        <p className="mb-5 flex items-start gap-3 rounded-[16px] bg-tint px-4 py-3.5 text-sm text-mut2">
          <ShieldCheck size={18} className="mt-0.5 shrink-0" />
          <span>
            <strong className="text-ink">Conta {pol.data.porte}.</strong> {pol.data.resumo}
            {pol.data.usuarios_ocupados != null && (
              <span className="mt-1 block text-xs text-mut3">
                {pol.data.usuarios_ocupados} de {pol.data.max_usuarios} acessos em uso.
              </span>
            )}
          </span>
        </p>
      )}

      {souAdmin &&
        (nova ? (
          <NovoMembro
            papeis={pol.data?.papeis_convidaveis ?? ["operador", "consulta"]}
            exigeAlcada={pol.data?.operador_exige_alcada ?? true}
            onFechar={() => setNova(false)}
          />
        ) : (
          <button className="btn btn-ink mb-5 w-full gap-2" onClick={() => setNova(true)}>
            <UserPlus size={18} /> Convidar pessoa
          </button>
        ))}

      <section className="surface px-5 py-2">
        {q.isLoading ? (
          <TxSkeleton n={4} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>
              {(q.error as Error).message || "Não foi possível carregar a equipe."}
            </ErrorBox>
          </div>
        ) : !ativos.length ? (
          <Empty title="Sem pessoas ainda" hint="Convide quem vai operar a conta." />
        ) : (
          <ul className="divide-y divide-border">
            {ativos.map((m) => (
              <Linha key={m.id} m={m} podeGerir={souAdmin && !m.eu} />
            ))}
          </ul>
        )}
      </section>

      {encerrados.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-mut3">
            Acessos encerrados ({encerrados.length})
          </summary>
          <ul className="surface mt-2 divide-y divide-border px-5 py-2 opacity-70">
            {encerrados.map((m) => (
              <Linha key={m.id} m={m} podeGerir={false} />
            ))}
          </ul>
        </details>
      )}

      <p className="mt-4 flex items-start gap-3 rounded-[16px] bg-tint px-4 py-3.5 text-sm text-mut2">
        <ShieldCheck size={18} className="mt-0.5 shrink-0" />
        Dupla autorização (maker-checker): pagamentos acima da alçada de quem lançou ficam pendentes
        até um administrador ou aprovador confirmar. Quem lançou nunca aprova a própria operação.
      </p>
    </div>
  );
}

function Linha({ m, podeGerir }: { m: MembroEquipe; podeGerir: boolean }) {
  const qc = useQueryClient();
  const [rosto, setRosto] = useState(false);
  const mut = useMutation({
    mutationFn: ({ acao, prova }: { acao: AcaoMembro; prova?: ProvaBiometrica }) =>
      mudarAcessoMembro(m.id, acao, prova),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["equipe"] });
      void qc.invalidateQueries({ queryKey: ["politica"] });
    },
  });
  const st = STATUS[m.status];
  const convite = m.status === "pendente" || m.status === "aguardando";

  return (
    <li className="py-3.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-sm font-semibold text-ink">
            {iniciais(m.nome)}
          </span>
          <div className="min-w-0">
            <p className="flex items-center gap-2 truncate font-medium text-ink">
              {m.nome}
              {m.eu && (
                <span className="rounded-full bg-tint px-1.5 text-[10px] text-mut2">você</span>
              )}
            </p>
            <p className="truncate text-xs text-mut3">
              {[m.cargo, m.cpf, m.email].filter(Boolean).join(" · ")}
            </p>
            {st ? (
              <p className={cn("text-[11px] font-medium", st.cor)}>{st.rotulo}</p>
            ) : (
              m.ultimo_acesso_em && (
                <p className="text-[11px] text-mut3">último acesso {fmtData(m.ultimo_acesso_em)}</p>
              )
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <span
            className={cn(
              "inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
              CORES_PAPEL[m.papel],
            )}
          >
            {PAPEIS[m.papel]}
          </span>
          <p className="mt-1 text-[11px] text-mut3">
            {m.papel === "consulta"
              ? "sem movimentação"
              : m.alcada == null
                ? "sem limite"
                : m.alcada === 0
                  ? "tudo passa por aprovação"
                  : `até ${fmtBRL(m.alcada)}`}
          </p>
        </div>
      </div>

      {podeGerir && m.status !== "revogado" && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-[52px] text-xs font-semibold">
          {m.status === "ativo" && (
            <button
              className="text-ink underline underline-offset-4"
              disabled={mut.isPending}
              onClick={() => mut.mutate({ acao: "suspender" })}
            >
              Suspender
            </button>
          )}
          {m.status === "suspenso" && (
            <button
              className="text-ink underline underline-offset-4"
              disabled={mut.isPending}
              onClick={() => (MODO_API ? setRosto(true) : mut.mutate({ acao: "reativar" }))}
            >
              Reativar
            </button>
          )}
          <button
            className="text-err underline underline-offset-4"
            disabled={mut.isPending}
            onClick={() => mut.mutate({ acao: "revogar" })}
          >
            {convite ? "Cancelar convite" : "Encerrar acesso"}
          </button>
        </div>
      )}
      {mut.isError && (
        <div className="mt-2">
          <ErrorBox>{(mut.error as Error).message}</ErrorBox>
        </div>
      )}
      {rosto && (
        <LivenessCheck
          onClose={() => setRosto(false)}
          onSuccess={(prova) => {
            setRosto(false);
            mut.mutate({ acao: "reativar", prova });
          }}
        />
      )}
    </li>
  );
}

function NovoMembro({
  papeis,
  exigeAlcada,
  onFechar,
}: {
  papeis: PapelVinculo[];
  exigeAlcada: boolean;
  onFechar: () => void;
}) {
  const qc = useQueryClient();
  const [nome, setNome] = useState("");
  const [cpf, setCpf] = useState("");
  const [email, setEmail] = useState("");
  const [cargo, setCargo] = useState("");
  const [papel, setPapel] = useState<PapelVinculo>(
    papeis.includes("operador") ? "operador" : papeis[0]!,
  );
  const [alcadaStr, setAlcadaStr] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [rosto, setRosto] = useState<ConvidarPayload | null>(null);
  const [enviado, setEnviado] = useState<MembroEquipe | null>(null);

  const mut = useMutation({
    mutationFn: convidarMembro,
    onSuccess: (m) => {
      void qc.invalidateQueries({ queryKey: ["equipe"] });
      void qc.invalidateQueries({ queryKey: ["politica"] });
      void qc.invalidateQueries({ queryKey: ["pendentes"] });
      setEnviado(m);
    },
    onError: (e: Error) => setErro(e.message),
  });

  const semAlcada = papel === "admin" || papel === "consulta";

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (nome.trim().length < 3) return setErro("Informe o nome completo.");
    if (cpf.replace(/\D/g, "").length !== 11) return setErro("CPF incompleto.");
    let alcada: number | null = null;
    if (!semAlcada) {
      if (alcadaStr.trim()) alcada = parseValor(alcadaStr) || 0;
      else if (papel === "operador") alcada = exigeAlcada ? NaN : 0;
    }
    if (Number.isNaN(alcada)) return setErro("Defina a alçada do operador.");
    const payload: ConvidarPayload = {
      nome: nome.trim(),
      cpf: cpf.replace(/\D/g, ""),
      papel,
      alcada,
      ...(email.trim() ? { email: email.trim() } : {}),
      ...(cargo.trim() ? { cargo: cargo.trim() } : {}),
    };
    // Dar poder (admin, aprovador, alçada) exige o rosto de quem concede.
    const sensivel = papel !== "consulta" && !(papel === "operador" && alcada === 0);
    if (MODO_API && sensivel) setRosto(payload);
    else mut.mutate(payload);
  }

  if (enviado)
    return (
      <section className="surface enter mb-5 p-5">
        <h2 className="text-lg text-ink">Convite enviado</h2>
        <p className="mt-1 text-sm text-mut2">
          {enviado.status === "aguardando"
            ? "Como é uma conta de grande empresa, outro administrador precisa aprovar este acesso em Aprovações. Depois disso, a pessoa aceita."
            : `${enviado.nome} verá o convite ao entrar na Astro com o próprio CPF e aceita com o rosto. Se ainda não tem conta, é só abrir uma.`}
        </p>
        <button className="btn btn-ghost mt-4 w-full" onClick={onFechar}>
          Fechar
        </button>
      </section>
    );

  return (
    <form onSubmit={enviar} className="surface enter mb-5 space-y-4 p-5">
      <h2 className="text-lg text-ink">Convidar pessoa</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome completo" id="m-nome">
          <input
            id="m-nome"
            className="field"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </Field>
        <Field label="CPF" id="m-cpf" hint="O acesso fica preso a este CPF.">
          <input
            id="m-cpf"
            inputMode="numeric"
            className="field tabular"
            value={cpf}
            onChange={(e) => setCpf(maskDoc(e.target.value, "PF"))}
            placeholder="000.000.000-00"
          />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="E-mail (opcional)" id="m-email">
          <input
            id="m-email"
            type="email"
            className="field"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Cargo (opcional)" id="m-cargo">
          <input
            id="m-cargo"
            className="field"
            value={cargo}
            onChange={(e) => setCargo(e.target.value)}
            placeholder="Financeiro, Contabilidade…"
          />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Papel" id="m-papel">
          <select
            id="m-papel"
            className="field"
            value={papel}
            onChange={(e) => setPapel(e.target.value as PapelVinculo)}
          >
            {papeis.map((p) => (
              <option key={p} value={p}>
                {PAPEIS[p]}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Alçada por operação (R$)"
          id="m-alcada"
          hint={
            papel === "admin"
              ? "Administrador não tem alçada."
              : papel === "consulta"
                ? "Só consulta não movimenta dinheiro."
                : papel === "aprovador"
                  ? "Até quanto pode aprovar. Vazio = sem limite."
                  : "Acima disso, outra pessoa aprova."
          }
        >
          <input
            id="m-alcada"
            inputMode="decimal"
            className="field tabular"
            value={semAlcada ? "" : alcadaStr}
            onChange={(e) => setAlcadaStr(e.target.value)}
            placeholder={semAlcada ? "—" : "0,00"}
            disabled={semAlcada}
          />
        </Field>
      </div>
      {erro && <ErrorBox>{erro}</ErrorBox>}
      <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
        <button type="button" className="btn btn-ghost" onClick={onFechar}>
          Cancelar
        </button>
        <button className="btn btn-ink gap-2" disabled={mut.isPending}>
          <Plus size={18} /> {mut.isPending ? "Enviando…" : "Enviar convite"}
        </button>
      </div>
      {rosto && (
        <LivenessCheck
          onClose={() => setRosto(null)}
          onSuccess={(prova) => {
            const payload = rosto;
            setRosto(null);
            mut.mutate({ ...payload, biometria: prova });
          }}
        />
      )}
    </form>
  );
}
