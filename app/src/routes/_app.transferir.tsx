import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Clock, ScanFace } from "lucide-react";
import { consultarDestino, transferir } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, parseValor } from "@/lib/format";
import type { CarteiraInfo, ProvaBiometrica } from "@/lib/types";
import { ErrorBox, Field, PageTitle, ValueRow } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/_app/transferir")({
  head: () => ({
    meta: [
      { title: "Transferir — PayFlow" },
      {
        name: "description",
        content: "Pix por chave ou conta, com verificação facial em valores altos.",
      },
      { property: "og:title", content: "Transferir — PayFlow" },
      { property: "og:description", content: "Pix por chave ou conta." },
    ],
  }),
  component: Transferir,
});

const LIMITE_FACIAL = 500;

/**
 * Pix/transferência. Transferência NÃO tem split: imposto só é retido quando você
 * paga uma cobrança com nota fiscal. Acima de R$ 500 pedimos verificação facial;
 * em conta de empresa, acima da sua alçada a operação vai para aprovação.
 */
function Transferir() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { conta } = useAuth();
  const [destino, setDestino] = useState("");
  const [valorStr, setValorStr] = useState("");
  const [info, setInfo] = useState<CarteiraInfo | null>(null);
  const [liveness, setLiveness] = useState(false);
  const [pendente, setPendente] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const valor = parseValor(valorStr);
  const precisaFacial = valor > LIMITE_FACIAL;
  const acimaDaAlcada = conta?.tipo === "PJ" && conta.alcada != null && valor > conta.alcada;

  async function revisar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!destino.trim()) return setErro("Informe a chave Pix ou o número da conta.");
    if (!(valor > 0)) return setErro("Informe um valor válido.");
    setLoading(true);
    try {
      setInfo(await consultarDestino(destino));
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function enviar(prova: ProvaBiometrica | null) {
    if (!info?.destino) return;
    setErro(null);
    setLoading(true);
    try {
      const r = await transferir({ destino: info.destino, valor, biometria: prova });
      qc.invalidateQueries();
      if (r.tipo === "pendente") setPendente(r.mensagem);
      else nav({ to: "/comprovante/$id", params: { id: String(r.transacao.id) } });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function confirmar() {
    if (precisaFacial && !acimaDaAlcada) setLiveness(true);
    else void enviar(null);
  }

  if (pendente)
    return (
      <div className="enter mx-auto max-w-md text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-tax-bg text-tax2">
          <Clock size={28} />
        </div>
        <h1 className="mt-5 text-2xl text-ink">Enviado para aprovação</h1>
        <p className="mt-2 text-sm text-muted-foreground">{pendente}</p>
        <Link to="/inicio" className="btn btn-ink mt-6 w-full">
          Voltar ao início
        </Link>
      </div>
    );

  return (
    <div className="enter">
      <PageTitle sub="Por chave Pix (CPF, CNPJ, e-mail, celular ou aleatória) ou número da conta.">
        Transferir
      </PageTitle>

      {!info ? (
        <form onSubmit={revisar} className="surface space-y-4 p-5 md:p-7">
          <Field label="Chave Pix ou conta" id="destino" hint="Ex.: e-mail, CPF ou 12345678-9.">
            <input
              id="destino"
              className="field"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
              placeholder="Chave Pix ou número da conta"
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
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">Para</p>
                <p className="truncate text-lg font-semibold text-ink">{info.nome}</p>
                {info.documento && <p className="text-xs text-mut3">{info.documento}</p>}
              </div>
              <span className="shrink-0 rounded-full bg-tint px-3 py-1 text-xs font-semibold text-mut2">
                {info.tipo === "PJ" ? "Empresa" : "Pessoa física"}
              </span>
            </div>
            <div className="mt-5 divide-y divide-border">
              <ValueRow label="Valor" value={valor} strong />
            </div>
            <p className="mt-3 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
              Transferência não tem retenção de imposto: {info.nome} recebe {fmtBRL(valor)}.
              {info.tipo === "PJ" &&
                " Se for a compra de um produto ou serviço, peça a cobrança da empresa: aí a CBS e o IBS da nota são separados no pagamento."}
            </p>
            {acimaDaAlcada && (
              <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
                Acima da sua alçada ({fmtBRL(conta?.alcada ?? 0)}): a transferência vai para
                aprovação de outra pessoa da empresa.
              </p>
            )}
            {precisaFacial && !acimaDaAlcada && (
              <p className="mt-3 flex items-center gap-2 text-sm text-mut2">
                <ScanFace size={16} /> Acima de {fmtBRL(LIMITE_FACIAL)} pedimos verificação facial.
              </p>
            )}
          </section>

          {erro && <ErrorBox>{erro}</ErrorBox>}
          <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
            <button
              className="btn btn-ghost"
              onClick={() => {
                setInfo(null);
                setErro(null);
              }}
            >
              Voltar
            </button>
            <button className="btn btn-ink" onClick={confirmar} disabled={loading}>
              {loading
                ? "Enviando…"
                : acimaDaAlcada
                  ? "Enviar para aprovação"
                  : "Confirmar transferência"}
            </button>
          </div>
        </div>
      )}

      {liveness && (
        <LivenessCheck
          onClose={() => setLiveness(false)}
          onSuccess={(prova) => {
            setLiveness(false);
            void enviar(prova);
          }}
        />
      )}
    </div>
  );
}
