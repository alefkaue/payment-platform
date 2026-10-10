import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowLeft, Check, Lock, Plane, ScanFace, Sparkles } from "lucide-react";
import {
  buscarVoos,
  comprarPassagem,
  minhaConta,
  pontosDaCompra,
  resgatarPassagem,
  type Resgate,
} from "@/lib/api";
import { calcularSplit } from "@/lib/split";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtPontos } from "@/lib/format";
import type { ProvaBiometrica, Voo } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, SplitBar, ValueRow } from "@/components/payflow/ui";
import { VooCard } from "./cartoes-beneficios";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/_app/viagens")({
  head: () => ({
    meta: [
      { title: "Viagens — Astro" },
      { name: "description", content: "Passagens aéreas pagando em reais ou com pontos Astro." },
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
  const [liveness, setLiveness] = useState(false);
  const [resgate, setResgate] = useState<Resgate | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState<null | "reais" | "pontos">(null);

  const q = useQuery({
    queryKey: ["voos", origem, destino],
    queryFn: () => buscarVoos(origem || undefined, destino || undefined),
  });
  const saldo = useQuery({ queryKey: ["conta", conta?.numero], queryFn: minhaConta });
  const pontos = saldo.data?.pontos ?? 0;

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

  if (resgate) {
    return (
      <div className="enter mx-auto max-w-md text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-tint text-pos">
          <Check size={28} strokeWidth={2.5} />
        </div>
        <h1 className="mt-5 text-2xl text-ink">Passagem emitida com pontos</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {resgate.voo.origem} → {resgate.voo.destino} · {resgate.voo.companhia} ·{" "}
          {resgate.voo.saida}
        </p>
        <section className="surface mt-6 space-y-2 p-5 text-left text-sm">
          <div className="flex justify-between">
            <span className="text-mut3">Localizador</span>
            <span className="font-mono font-semibold text-ink">{resgate.localizador}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-mut3">Pontos usados</span>
            <span className="tabular font-semibold text-ink">
              {fmtPontos(resgate.pontos_usados)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-mut3">Saldo de pontos</span>
            <span className="tabular font-semibold text-ink">
              {fmtPontos(resgate.saldo_pontos)}
            </span>
          </div>
          <p className="pt-2 text-xs text-mut3">Seu saldo em reais não foi alterado.</p>
        </section>
        <Link to="/inicio" className="btn btn-ink mt-6 w-full">
          Voltar ao início
        </Link>
      </div>
    );
  }

  if (sel) {
    const split = calcularSplit(sel.preco, "PJ");
    const precisaFacial = sel.preco > 500;
    const podeResgatar = pontos >= sel.milhas;

    const finalizar = async (biometria: ProvaBiometrica | null) => {
      setLoading("reais");
      try {
        const t = await comprarPassagem({ voo_id: sel.id, biometria });
        qc.invalidateQueries();
        nav({ to: "/comprovante/$id", params: { id: String(t.id) } });
      } catch (e) {
        setErro((e as Error).message);
      } finally {
        setLoading(null);
      }
    };
    const comprar = () => {
      setErro(null);
      if (precisaFacial) setLiveness(true);
      else void finalizar(null);
    };
    const resgatar = async () => {
      setErro(null);
      setLoading("pontos");
      try {
        const r = await resgatarPassagem(sel.id);
        qc.invalidateQueries();
        setResgate(r);
      } catch (e) {
        setErro((e as Error).message);
      } finally {
        setLoading(null);
      }
    };
    return (
      <div className="enter mx-auto max-w-md">
        <button
          onClick={() => {
            setSel(null);
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
              <ValueRow label="CBS da nota → Fisco" value={split.cbs} tax />
              <ValueRow label="IBS da nota → Fisco" value={split.ibs} tax />
              <ValueRow label={`${sel.merchant_nome} recebe`} value={split.liquido} strong />
            </div>
            <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
              Pagando em reais, você ganha {fmtPontos(pontosDaCompra(sel.preco))} pontos nesta
              compra.
            </p>
          </div>

          {precisaFacial && (
            <p className="mt-4 flex items-center gap-2 text-sm text-mut2">
              <ScanFace size={16} /> Acima de R$ 500 confirmamos com verificação facial.
            </p>
          )}
          {erro && (
            <div className="mt-4">
              <ErrorBox>{erro}</ErrorBox>
            </div>
          )}
          <button onClick={comprar} disabled={loading !== null} className="btn btn-ink mt-5 w-full">
            {loading === "reais" ? "Emitindo…" : `Comprar passagem · ${fmtBRL(sel.preco)}`}
          </button>

          <div className="mt-5 rounded-[16px] border border-line2 p-4">
            <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
              <Sparkles size={15} className="text-ink" /> Ou use seus pontos
            </p>
            <p className="mt-1 text-sm text-mut2">
              Este voo sai por {fmtPontos(sel.milhas)} pontos. Você tem {fmtPontos(pontos)}.
            </p>
            <button
              onClick={() => void resgatar()}
              disabled={loading !== null || !podeResgatar}
              className="btn btn-ghost mt-3 w-full"
            >
              {loading === "pontos"
                ? "Emitindo…"
                : podeResgatar
                  ? `Resgatar com ${fmtPontos(sel.milhas)} pontos`
                  : `Faltam ${fmtPontos(sel.milhas - pontos)} pontos`}
            </button>
          </div>
        </div>
        {liveness && (
          <LivenessCheck
            onClose={() => setLiveness(false)}
            onSuccess={(prova) => {
              setLiveness(false);
              void finalizar(prova);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="enter">
      <PageTitle sub="Pague em reais e acumule pontos, ou use seus pontos para voar. O imposto da passagem é retido no ato.">
        Viagens
      </PageTitle>

      <p className="mb-4 inline-flex items-center gap-1.5 rounded-full bg-tint px-3 py-1.5 text-sm text-ink">
        <Sparkles size={14} className="text-ink" /> {fmtPontos(pontos)} pontos disponíveis
      </p>

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
