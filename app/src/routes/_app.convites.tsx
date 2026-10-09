import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Building2, ScanFace, X } from "lucide-react";
import { aceitarConvite, meusConvites, MODO_API, recusarConvite } from "@/lib/api";
import { PAPEIS } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL } from "@/lib/format";
import type { ConviteRecebido, ProvaBiometrica } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/_app/convites")({
  head: () => ({ meta: [{ title: "Convites de empresas — Astro" }] }),
  component: Convites,
});

/**
 * Convites que a pessoa logada recebeu para acessar contas de empresa. O
 * convite é preso ao CPF dela; aceitar exige o rosto (e a identidade já
 * verificada). Depois de aceito, a empresa aparece no seletor de contas.
 */
function Convites() {
  const q = useQuery({ queryKey: ["convites"], queryFn: meusConvites });

  return (
    <div className="enter">
      <PageTitle sub="Empresas que convidaram você para acessar a conta delas.">
        Convites de empresas
      </PageTitle>
      {!MODO_API ? (
        <div className="surface">
          <Empty
            title="Disponível com o servidor"
            hint="Na demonstração, a equipe da empresa é simulada direto em Equipe & alçadas."
          />
        </div>
      ) : q.isLoading ? (
        <div className="surface px-5 py-2">
          <TxSkeleton n={2} />
        </div>
      ) : q.isError ? (
        <ErrorBox>{(q.error as Error).message}</ErrorBox>
      ) : !q.data?.length ? (
        <div className="surface">
          <Empty
            title="Nenhum convite"
            hint="Quando uma empresa convidar o seu CPF, o convite aparece aqui."
          />
        </div>
      ) : (
        <div className="space-y-4">
          {q.data.map((c) => (
            <Cartao key={c.id} c={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function Cartao({ c }: { c: ConviteRecebido }) {
  const qc = useQueryClient();
  const { conta, pessoa, entrar } = useAuth();
  const [rosto, setRosto] = useState(false);
  const aceitar = useMutation({
    mutationFn: (prova: ProvaBiometrica) => aceitarConvite(c.id, prova),
    onSuccess: (contas) => {
      // a empresa entra no seletor de contas sem precisar sair e entrar de novo
      if (conta) entrar({ contas, conta, ...(pessoa ? { pessoa } : {}) });
      void qc.invalidateQueries({ queryKey: ["convites"] });
    },
  });
  const recusar = useMutation({
    mutationFn: () => recusarConvite(c.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["convites"] }),
  });
  const erro = (aceitar.error ?? recusar.error) as Error | null;

  return (
    <section className="surface p-5">
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-tint text-ink">
          <Building2 size={20} />
        </span>
        <div className="min-w-0">
          <p className="font-semibold text-ink">{c.empresa}</p>
          <p className="text-sm text-mut2">
            {PAPEIS[c.papel]}
            {c.papel !== "admin" &&
              c.papel !== "consulta" &&
              (c.alcada == null ? " · sem limite" : ` · até ${fmtBRL(c.alcada)} por operação`)}
          </p>
          {c.convidado_por && (
            <p className="mt-1 text-xs text-mut3">Convidado por {c.convidado_por}</p>
          )}
        </div>
      </div>
      {erro && (
        <div className="mt-3">
          <ErrorBox>{erro.message}</ErrorBox>
        </div>
      )}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <button
          className="btn btn-ghost gap-2"
          disabled={aceitar.isPending || recusar.isPending}
          onClick={() => recusar.mutate()}
        >
          <X size={18} /> Recusar
        </button>
        <button
          className="btn btn-ink gap-2"
          disabled={aceitar.isPending || recusar.isPending}
          onClick={() => setRosto(true)}
        >
          <ScanFace size={18} /> {aceitar.isPending ? "Aceitando…" : "Aceitar"}
        </button>
      </div>
      {rosto && (
        <LivenessCheck
          onClose={() => setRosto(false)}
          onSuccess={(prova) => {
            setRosto(false);
            aceitar.mutate(prova);
          }}
        />
      )}
    </section>
  );
}
