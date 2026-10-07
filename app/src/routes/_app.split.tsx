import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, Check, Info, ShieldCheck, TrendingUp } from "lucide-react";
import {
  ALIQUOTA_PLENA,
  aliquotasDoAno,
  calcularSplit,
  CRONOGRAMA,
  REGIMES,
  type RegimeTributario,
  VIGENCIA_ATUAL,
} from "@/lib/split";
import { useAuth } from "@/lib/auth";
import { fmtBRL, parseValor } from "@/lib/format";
import type { TipoConta, Vigencia } from "@/lib/types";
import { Field, MetricTile, PageTitle, SplitBar } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/split")({
  head: () => ({
    meta: [
      { title: "Entenda o split — PayFlow" },
      {
        name: "description",
        content: "O imposto da Reforma Tributária (IBS/CBS) separado no ato da venda.",
      },
    ],
  }),
  component: SplitHub,
});

const pct = (n: number) => `${(n * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

function SplitHub() {
  const { conta } = useAuth();
  const ehPJ = conta?.tipo === "PJ";

  return (
    <div className="enter space-y-7">
      <PageTitle sub="O imposto da Reforma Tributária (IBS/CBS) separado no ato da venda — não depois, na guia.">
        Entenda o split
      </PageTitle>

      {/* O que é */}
      <section className="surface overflow-hidden p-6">
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-tax-bg text-tax2">
            <Info size={20} />
          </span>
          <h2 className="text-lg text-ink">O que é o split</h2>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-mut2">
          Na Reforma (LC 214/2025), quando um cliente paga uma venda{" "}
          <strong>com nota fiscal</strong>, o banco separa a <strong>CBS</strong> (federal) e o{" "}
          <strong>IBS</strong> (estados/municípios) que estão destacados na nota e envia direto ao
          Fisco. A empresa recebe o valor <strong>líquido</strong>. Transferência comum (Pix entre
          contas, reembolso, empréstimo) <strong>nunca</strong> tem split.
        </p>

        <div className="mt-5 rounded-[16px] bg-tint p-4">
          <p className="text-xs text-mut3">
            Exemplo de uma venda com nota · alíquotas de {VIGENCIA_ATUAL} (regime padrão)
          </p>
          <ExemploBarra />
        </div>
      </section>

      {/* Não é imposto a mais */}
      <section className="surface p-6">
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-pos">
            <ShieldCheck size={20} />
          </span>
          <h2 className="text-lg text-ink">O split não é dinheiro a mais</h2>
        </div>
        <ul className="mt-4 space-y-3">
          {[
            "Não cobra nada além do imposto que já era devido na venda.",
            "Só recolhe na hora, em vez de depois — a apuração continua, mas sai quase pronta.",
            "Transferência entre contas (sócio, reembolso) nunca sofre retenção.",
            "Seus créditos de compras entram na apuração e o que sobrar volta como restituição.",
          ].map((t) => (
            <li key={t} className="flex items-start gap-3 text-sm text-mut2">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[color-mix(in_oklab,var(--pos)_15%,transparent)] text-pos">
                <Check size={13} strokeWidth={3} />
              </span>
              {t}
            </li>
          ))}
        </ul>
      </section>

      {/* Linha do tempo da Reforma */}
      <section className="surface p-6">
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-ink">
            <TrendingUp size={20} />
          </span>
          <div>
            <h2 className="text-lg text-ink">A transição, ano a ano</h2>
            <p className="text-xs text-mut3">
              O imposto sobe aos poucos até o regime pleno em 2033.
            </p>
          </div>
        </div>
        <Cronograma />
      </section>

      {/* Simulador */}
      <Simulador ehPJ={ehPJ} setor={conta?.setor} />

      {ehPJ && (
        <section className="rounded-[20px] bg-ink p-6 text-ink-foreground shadow-lift">
          <h2 className="text-lg font-semibold">Na sua conta, o split é invisível</h2>
          <p className="mt-2 text-sm opacity-80">
            Cada cobrança paga já chega líquida, com o imposto conciliado à nota. Você vê o que foi
            retido, o que já foi repassado e a projeção de crédito no card “Imposto das suas
            vendas”.
          </p>
        </section>
      )}
    </div>
  );
}

function ExemploBarra() {
  const r = calcularSplit(10000, "PJ", VIGENCIA_ATUAL, "padrao");
  return (
    <div className="mt-3">
      <SplitBar liquido={r.liquido} imposto={r.imposto_total} />
      <div className="mt-2 flex justify-between text-sm">
        <span className="font-semibold text-pos">Você recebe {fmtBRL(r.liquido)}</span>
        <span className="text-tax">IBS/CBS {fmtBRL(r.imposto_total)}</span>
      </div>
      <p className="mt-1 text-[11px] text-mut3">Sobre uma venda de {fmtBRL(r.valor_bruto)}.</p>
    </div>
  );
}

function Cronograma() {
  const anos = Object.keys(CRONOGRAMA).map(Number) as Vigencia[];
  const max = ALIQUOTA_PLENA;
  return (
    <ol className="mt-5 space-y-2.5">
      {anos.map((ano) => {
        const a = aliquotasDoAno(ano);
        const total = a.cbs + a.ibs;
        const atual = ano === VIGENCIA_ATUAL;
        return (
          <li key={ano} className="flex items-center gap-3">
            <span
              className={cn(
                "w-11 shrink-0 text-sm font-semibold tabular",
                atual ? "text-ink" : "text-mut3",
              )}
            >
              {ano}
            </span>
            <div className="h-7 flex-1 overflow-hidden rounded-full bg-tint">
              <div
                className={cn(
                  "flex h-full items-center justify-end rounded-full px-2 transition-all",
                  atual ? "bg-marca" : "bg-ink/80",
                )}
                style={{ width: `${Math.max((total / max) * 100, 12)}%` }}
              >
                <span
                  className={cn(
                    "text-[11px] font-semibold tabular",
                    atual ? "text-ink" : "text-ink-foreground",
                  )}
                >
                  {pct(total)}
                </span>
              </div>
            </div>
            {atual && (
              <span className="shrink-0 rounded-full bg-tax-bg px-2 py-0.5 text-[10px] font-bold uppercase text-tax2">
                agora
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Simulador({ ehPJ, setor }: { ehPJ: boolean; setor: string | undefined }) {
  const [valorStr, setValorStr] = useState("10.000,00");
  const [tipo, setTipo] = useState<TipoConta>(ehPJ ? "PJ" : "PF");
  const [ano, setAno] = useState<Vigencia>(VIGENCIA_ATUAL);
  const [regime, setRegime] = useState<RegimeTributario>("padrao");
  const valor = parseValor(valorStr) || 0;
  const r = calcularSplit(valor, tipo, ano, regime);

  return (
    <section className="surface p-6">
      <h2 className="text-lg text-ink">Simule o split</h2>
      <p className="text-xs text-mut3">Mesmo motor de cálculo do app e do backend.</p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Valor da venda (R$)" id="sim-valor">
          <input
            id="sim-valor"
            inputMode="decimal"
            className="field tabular"
            value={valorStr}
            onChange={(e) => setValorStr(e.target.value)}
            placeholder="0,00"
          />
        </Field>
        <Field label="Quem vende" id="sim-tipo">
          <select
            id="sim-tipo"
            className="field"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoConta)}
          >
            <option value="PF">Pessoa (PF) — sem split</option>
            <option value="PJ">Empresa com nota (PJ)</option>
          </select>
        </Field>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Ano da transição" id="sim-ano">
          <select
            id="sim-ano"
            className="field"
            value={ano}
            onChange={(e) => setAno(Number(e.target.value))}
          >
            {(Object.keys(CRONOGRAMA).map(Number) as number[]).map((y) => (
              <option key={y} value={y}>
                {y}
                {y === VIGENCIA_ATUAL ? " (atual)" : ""}
                {y === 2033 ? " — pleno" : ""}
              </option>
            ))}
          </select>
        </Field>
        {tipo === "PJ" && (
          <Field label="Regime do setor" id="sim-regime" hint={REGIMES[regime].exemplos}>
            <select
              id="sim-regime"
              className="field"
              value={regime}
              onChange={(e) => setRegime(e.target.value as RegimeTributario)}
            >
              {(Object.keys(REGIMES) as RegimeTributario[]).map((k) => (
                <option key={k} value={k}>
                  {REGIMES[k].label}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>

      <div className="mt-6 rounded-[16px] bg-tint p-4">
        <SplitBar liquido={r.liquido} imposto={r.imposto_total} />
        <div className="mt-4 grid grid-cols-2 gap-3">
          <MetricTile label="Destino recebe (líquido)" value={fmtBRL(r.liquido)} tone="pos" />
          <MetricTile label="Imposto → Fisco" value={fmtBRL(r.imposto_total)} tone="tax" />
          {r.aplicou_split && (
            <>
              <MetricTile label="CBS da nota" value={fmtBRL(r.cbs)} />
              <MetricTile label="IBS da nota" value={fmtBRL(r.ibs)} />
            </>
          )}
        </div>
        {!r.aplicou_split && (
          <p className="mt-3 flex items-center gap-2 text-sm text-mut2">
            <ArrowRight size={15} /> Sem venda de empresa com nota, não há retenção: o valor chega
            cheio.
          </p>
        )}
        {setor && tipo === "PJ" && (
          <p className="mt-3 text-[11px] text-mut3">
            Seu setor: {setor}. Na venda real, o imposto vem calculado na própria nota (por
            NCM/NBS).
          </p>
        )}
      </div>
    </section>
  );
}
