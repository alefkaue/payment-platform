import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { consultarCarteira, transferir } from "@/lib/api";
import { calcularSplit } from "@/lib/split";
import { fmtBRL, fmtId, parseValor } from "@/lib/format";
import type { CarteiraInfo } from "@/lib/types";
import {
  ErrorBox,
  Field,
  PageTitle,
  SelfieCapture,
  SplitBar,
  ValueRow,
} from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/transferir")({
  head: () => ({
    meta: [
      { title: "Transferir — PayFlow" },
      { name: "description", content: "Transfira com split automático de IBS/CBS para empresas." },
      { property: "og:title", content: "Transferir — PayFlow" },
      { property: "og:description", content: "Veja o imposto antes de confirmar." },
    ],
  }),
  component: Transferir,
});

function Transferir() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [destino, setDestino] = useState("");
  const [valorStr, setValorStr] = useState("");
  const [info, setInfo] = useState<CarteiraInfo | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const valor = parseValor(valorStr);
  const split = useMemo(
    () => (info && valor > 0 ? calcularSplit(valor, info.tipo) : null),
    [info, valor],
  );
  const precisaSelfie = valor > 500;

  async function revisar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const id = Number(destino.replace(/\D/g, ""));
    if (!id) return setErro("Informe a carteira de destino.");
    if (!(valor > 0)) return setErro("Informe um valor válido.");
    setLoading(true);
    try {
      setInfo(await consultarCarteira(id));
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function confirmar() {
    if (!info) return;
    setErro(null);
    if (precisaSelfie && !selfie)
      return setErro("Capture a selfie para confirmar valores acima de R$ 500.");
    setLoading(true);
    try {
      const t = await transferir({
        destino_carteira_id: info.carteira_id,
        valor,
        selfie: precisaSelfie ? selfie : null,
      });
      qc.invalidateQueries();
      nav({ to: "/comprovante/$id", params: { id: String(t.id) } });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="enter">
      <PageTitle sub="Para empresas, CBS e IBS são retidos no ato.">Transferir</PageTitle>

      {!info ? (
        <form onSubmit={revisar} className="surface space-y-4 p-5 md:p-7">
          <Field
            label="Carteira de destino (ID)"
            id="destino"
            hint="Experimente 2001 (PF) ou 3001 (PJ)."
          >
            <input
              id="destino"
              inputMode="numeric"
              className="field tabular"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
              placeholder="Ex.: 3001"
            />
          </Field>
          <Field label="Valor (R$)" id="valor">
            <input
              id="valor"
              inputMode="decimal"
              className="field tabular text-lg"
              value={valorStr}
              onChange={(e) => setValorStr(e.target.value)}
              placeholder="0,00"
            />
          </Field>
          {erro && <ErrorBox>{erro}</ErrorBox>}
          <button className="btn btn-ink w-full" disabled={loading}>
            {loading ? "Consultando…" : "Revisar"}
          </button>
        </form>
      ) : (
        <div className="space-y-4">
          <section className="surface enter p-5 md:p-7">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Para {fmtId(info.carteira_id)}</p>
                <p className="text-lg font-semibold text-ink">{info.nome}</p>
              </div>
              <span className="rounded-full bg-tint px-3 py-1 text-xs font-semibold text-mut2">
                {info.tipo === "PJ" ? "Empresa · PJ" : "Pessoa física · PF"}
              </span>
            </div>

            <div className="mt-5">
              <Field label="Valor (R$)" id="valor2">
                <input
                  id="valor2"
                  inputMode="decimal"
                  className="field tabular text-lg"
                  value={valorStr}
                  onChange={(e) => setValorStr(e.target.value)}
                />
              </Field>
            </div>

            {split && (
              <div className="mt-6">
                <SplitBar liquido={split.liquido} imposto={split.imposto_total} />
                <div className="mt-3 divide-y divide-border">
                  <ValueRow label="Você paga" value={split.valor_bruto} />
                  {split.aplicou_split && <ValueRow label="CBS → Governo" value={split.cbs} tax />}
                  {split.aplicou_split && <ValueRow label="IBS → Governo" value={split.ibs} tax />}
                  <ValueRow label="Destino recebe" value={split.liquido} strong />
                </div>
                {!split.aplicou_split ? (
                  <p className="mt-3 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
                    Destino PF — sem retenção de imposto.
                  </p>
                ) : (
                  <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
                    Vigência {split.vigencia} · imposto total {fmtBRL(split.imposto_total)} retido
                    no ato.
                  </p>
                )}
              </div>
            )}
          </section>

          {precisaSelfie && (
            <div className="enter">
              <SelfieCapture value={selfie} onChange={setSelfie} title="Confirme com uma selfie" />
            </div>
          )}

          {erro && <ErrorBox>{erro}</ErrorBox>}
          <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
            <button
              className="btn btn-ghost"
              onClick={() => {
                setInfo(null);
                setSelfie(null);
                setErro(null);
              }}
            >
              Voltar
            </button>
            <button className="btn btn-ink" onClick={confirmar} disabled={loading || !split}>
              {loading ? "Enviando…" : "Confirmar transferência"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
