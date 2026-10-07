import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, ShieldCheck, UserPlus } from "lucide-react";
import { convidarMembro, equipe } from "@/lib/api";
import { PAPEIS } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, iniciais, parseValor } from "@/lib/format";
import type { MembroEquipe, PapelVinculo } from "@/lib/types";
import { Empty, ErrorBox, Field, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/equipe")({
  head: () => ({ meta: [{ title: "Equipe & alçadas — PayFlow" }] }),
  component: Equipe,
});

const CORES_PAPEL: Record<PapelVinculo, string> = {
  admin: "bg-ink text-ink-foreground",
  aprovador: "bg-tax-bg text-tax2",
  operador: "bg-tint text-ink",
  consulta: "bg-tint text-mut2",
};

function Equipe() {
  const { conta } = useAuth();
  const [nova, setNova] = useState(false);
  const q = useQuery({ queryKey: ["equipe", conta?.numero], queryFn: equipe });

  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  return (
    <div className="enter">
      <PageTitle sub="Quem acessa a conta da empresa, com papel e alçada. Acima da alçada, outra pessoa aprova.">
        Equipe & alçadas
      </PageTitle>

      {nova ? (
        <NovoMembro onFechar={() => setNova(false)} />
      ) : (
        <button className="btn btn-ink mb-5 w-full gap-2" onClick={() => setNova(true)}>
          <UserPlus size={18} /> Adicionar pessoa
        </button>
      )}

      <section className="surface px-5 py-2">
        {q.isLoading ? (
          <TxSkeleton n={4} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>Não foi possível carregar a equipe.</ErrorBox>
          </div>
        ) : !q.data?.length ? (
          <Empty title="Sem pessoas ainda" hint="Adicione quem vai operar a conta." />
        ) : (
          <ul className="divide-y divide-border">
            {q.data.map((m) => (
              <Linha key={m.id} m={m} />
            ))}
          </ul>
        )}
      </section>

      <p className="mt-4 flex items-start gap-3 rounded-[16px] bg-tint px-4 py-3.5 text-sm text-mut2">
        <ShieldCheck size={18} className="mt-0.5 shrink-0" />
        Dupla autorização (maker-checker): pagamentos acima da alçada de quem lançou ficam pendentes
        até um administrador ou aprovador confirmar.
      </p>
    </div>
  );
}

function Linha({ m }: { m: MembroEquipe }) {
  return (
    <li className="flex items-center justify-between gap-3 py-3.5">
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
          <p className="truncate text-xs text-mut3">{m.email}</p>
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
          {m.alcada == null
            ? "sem limite"
            : m.alcada === 0
              ? "sem movimentação"
              : `até ${fmtBRL(m.alcada)}`}
        </p>
      </div>
    </li>
  );
}

function NovoMembro({ onFechar }: { onFechar: () => void }) {
  const qc = useQueryClient();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<PapelVinculo>("operador");
  const [alcadaStr, setAlcadaStr] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: convidarMembro,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["equipe"] });
      onFechar();
    },
    onError: (e: Error) => setErro(e.message),
  });

  const semLimite = papel === "admin" || papel === "aprovador";

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!nome.trim() || !email.trim()) return setErro("Preencha nome e e-mail.");
    const alcada = semLimite ? null : parseValor(alcadaStr || "0") || 0;
    mut.mutate({ nome: nome.trim(), email: email.trim(), papel, alcada });
  }

  return (
    <form onSubmit={enviar} className="surface enter mb-5 space-y-4 p-5">
      <h2 className="text-lg text-ink">Adicionar pessoa</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome" id="m-nome">
          <input
            id="m-nome"
            className="field"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </Field>
        <Field label="E-mail" id="m-email">
          <input
            id="m-email"
            type="email"
            className="field"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
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
            {(Object.keys(PAPEIS) as PapelVinculo[]).map((p) => (
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
            semLimite
              ? "Admin e aprovador não têm limite de alçada."
              : "Acima disso, outra pessoa aprova."
          }
        >
          <input
            id="m-alcada"
            inputMode="decimal"
            className="field tabular"
            value={semLimite ? "" : alcadaStr}
            onChange={(e) => setAlcadaStr(e.target.value)}
            placeholder={semLimite ? "Sem limite" : "0,00"}
            disabled={semLimite}
          />
        </Field>
      </div>
      {erro && <ErrorBox>{erro}</ErrorBox>}
      <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
        <button type="button" className="btn btn-ghost" onClick={onFechar}>
          Cancelar
        </button>
        <button className="btn btn-ink gap-2" disabled={mut.isPending}>
          <Plus size={18} /> {mut.isPending ? "Adicionando…" : "Adicionar à equipe"}
        </button>
      </div>
    </form>
  );
}
