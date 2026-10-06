import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowLeft, Lock, Plane } from "lucide-react";
import { buscarVoos, comprarPassagem } from "@/lib/api";
import { calcularSplit } from "@/lib/split";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtPontos } from "@/lib/format";
import type { Voo } from "@/lib/types";
import {
  Empty,
  ErrorBox,
  PageTitle,
  SelfieCapture,
  SplitBar,
  ValueRow,
  VooCard,
} from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/viagens")({
  head: () => ({
    meta: [
      { title: "Viagens — PayFlow" },
      { name: "description", content: "Passagens aéreas pagando em reais ou com pontos PayFlow." },
    ],
  }),
  component: Viagens,
});

function Viagens() {
  const { conta } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [origem, setOrigem] = useState("");
  const [destino, setDestino] = useState("");
  const [sel, setSel] = useState<Voo | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const q = useQuery({
    queryKey: ["voos", origem, destino],
    queryFn: () => buscarVoos(origem || undefined, destino || undefined),
  });

  const origens = useMemo(() => Array.from(new Set((q.data ?? []).map((v) => v.origem))), [q.data]);
  const destinos = useMemo(
    () => Array.from(new Set((q.data ?? []).map((v) => v.destino))),
    [q.data],
  );

  if (conta?.tipo === "PJ") {
    return (
      <div className="enter">
        <PageTitle>Viagens</PageTitle>
        <div className="surface flex items-start gap-3 p-6">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-mut2">
            <Lock size={18} />
          </div>
          <div>
            <p className="font-semibold text-ink">Benefício das contas Pessoa Física.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Passagens com pontos são exclusivas para contas PF.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (sel) {
    const split = calcularSplit(sel.preco, "PJ");
    const precisaSelfie = sel.preco > 500;
    const comprar = async () => {
      setErro(null);
      if (precisaSelfie && !selfie)
        return setErro("Capture a selfie para compras acima de R$ 500.");
      setLoading(true);
      try {
        const t = await comprarPassagem({ voo_id: sel.id, selfie: precisaSelfie ? selfie : null });
        qc.invalidateQueries();
        nav({ to: "/comprovante/$id", params: { id: String(t.id) } });
      } catch (e) {
        setErro((e as Error).message);
      } finally {
        setLoading(false);
      }
    };
    return (
      <div className="enter mx-auto max-w-md">
        <button
          onClick={() => {
            setSel(null);
            setSelfie(null);
            setErro(null);
          }}
          className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-mut2 hover:text-ink"
        >
          <ArrowLeft size={16} /> Voltar aos voos
        </button>
        <div className="surface p-5 md:p-6">
          <div className="flex items-center gap-2 text-sm font-medium text-mut2">
            <Plane size={16} /> {sel.companhia}
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div>
              <p className="text-2xl font-semibold tabular text-ink">{sel.saida}</p>
              <p className="text-xs text-mut3">
                {sel.origem} · {sel.origemCidade}
              </p>
            </div>
            <div className="mx-3 flex-1 border-t border-dashed border-line2" />
            <div className="text-right">
              <p className="text-2xl font-semibold tabular text-ink">{sel.chegada}</p>
              <p className="text-xs text-mut3">
                {sel.destino} · {sel.destinoCidade}
              </p>
            </div>
          </div>
          <p className="mt-2 text-xs text-mut3">
            {sel.duracao} · {sel.direto ? "voo direto" : "1 parada"}
          </p>

          <div className="mt-6">
            <SplitBar liquido={split.liquido} imposto={split.imposto_total} />
            <div className="mt-3 divide-y divide-border">
              <ValueRow label="Você paga" value={split.valor_bruto} />
              <ValueRow label="CBS → Governo" value={split.cbs} tax />
              <ValueRow label="IBS → Governo" value={split.ibs} tax />
              <ValueRow label={`${sel.merchant_nome} recebe`} value={split.liquido} strong />
            </div>
            <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
              Você ganha {fmtPontos(sel.milhas)} pontos nesta compra.
            </p>
          </div>

          {precisaSelfie && (
            <div className="mt-4">
              <SelfieCapture value={selfie} onChange={setSelfie} title="Confirme com uma selfie" />
            </div>
          )}
          {erro && (
            <div className="mt-4">
              <ErrorBox>{erro}</ErrorBox>
            </div>
          )}
          <button onClick={comprar} disabled={loading} className="btn btn-ink mt-5 w-full">
            {loading ? "Emitindo…" : `Comprar passagem · ${fmtBRL(sel.preco)}`}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="enter">
      <PageTitle sub="Pague em reais e acumule pontos. O imposto da passagem é retido no ato.">
        Viagens
      </PageTitle>

      <div className="surface mb-5 grid grid-cols-2 gap-3 p-4">
        <div>
          <label htmlFor="origem" className="text-sm font-medium text-mut2">
            Origem
          </label>
          <select
            id="origem"
            value={origem}
            onChange={(e) => setOrigem(e.target.value)}
            className="field mt-1.5"
          >
            <option value="">Qualquer</option>
            {origens.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="destino" className="text-sm font-medium text-mut2">
            Destino
          </label>
          <select
            id="destino"
            value={destino}
            onChange={(e) => setDestino(e.target.value)}
            className="field mt-1.5"
          >
            <option value="">Qualquer</option>
            {destinos.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      </div>

      {q.isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-[20px] bg-tint" />
          ))}
        </div>
      ) : q.isError ? (
        <ErrorBox>Não foi possível buscar voos.</ErrorBox>
      ) : !q.data?.length ? (
        <Empty title="Nenhum voo encontrado" hint="Tente outra combinação de origem e destino." />
      ) : (
        <div className="space-y-4">
          {q.data.map((v) => (
            <VooCard key={v.id} v={v} onSelect={() => setSel(v)} />
          ))}
        </div>
      )}
    </div>
  );
}
