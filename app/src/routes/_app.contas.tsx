import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Copy, FileText, Plus } from "lucide-react";
import { criarCobranca, listarFaturas } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, parseValor } from "@/lib/format";
import type { Cobranca, DirecaoFatura } from "@/lib/types";
import { Empty, ErrorBox, Field, MetricTile, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { FaturaRow } from "./_app.inicio";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/contas")({
  head: () => ({ meta: [{ title: "Contas — PayFlow" }] }),
  component: Contas,
});

function Contas() {
  const { conta } = useAuth();
  const [aba, setAba] = useState<DirecaoFatura>("receber");
  const [nova, setNova] = useState(false);
  const q = useQuery({ queryKey: ["faturas", conta?.numero], queryFn: () => listarFaturas() });

  // Contas a pagar/receber são um recurso da conta Empresa.
  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  const todas = q.data ?? [];
  const aReceber = todas.filter((f) => f.direcao === "receber");
  const aPagar = todas.filter((f) => f.direcao === "pagar");
  const totReceber = aReceber.reduce((a, f) => a + f.liquido, 0);
  const totPagar = aPagar.reduce((a, f) => a + f.valor_bruto, 0);
  const totCredito = aPagar.reduce((a, f) => a + f.credito_gerado, 0);
  const lista = aba === "receber" ? aReceber : aPagar;

  return (
    <div className="enter">
      <PageTitle sub="Faturas B2B conciliadas com a nota fiscal (NF-e). O imposto da nota é separado no ato.">
        Contas
      </PageTitle>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricTile label="A receber (líquido)" value={fmtBRL(totReceber)} tone="pos" />
        <MetricTile label="A pagar" value={fmtBRL(totPagar)} />
        <MetricTile
          label="Crédito a gerar"
          value={fmtBRL(totCredito)}
          tone="tax"
          hint="abate impostos na apuração"
        />
      </div>

      {nova ? (
        <NovaCobranca onFechar={() => setNova(false)} />
      ) : (
        <button className="btn btn-ink mt-5 w-full gap-2" onClick={() => setNova(true)}>
          <Plus size={18} /> Cobrar um cliente
        </button>
      )}

      <div role="tablist" className="mt-6 grid grid-cols-2 rounded-full bg-tint p-1">
        {(["receber", "pagar"] as const).map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={aba === d}
            onClick={() => setAba(d)}
            className={cn(
              "h-10 rounded-full text-sm font-semibold transition-colors duration-200",
              aba === d ? "bg-card text-ink shadow-soft" : "text-mut2 hover:text-ink",
            )}
          >
            {d === "receber" ? "A receber" : "A pagar"}
          </button>
        ))}
      </div>

      <section className="surface mt-4 px-5 py-2">
        {q.isLoading ? (
          <TxSkeleton n={4} />
        ) : q.isError ? (
          <div className="py-4">
            <ErrorBox>Não foi possível carregar as contas.</ErrorBox>
          </div>
        ) : !lista.length ? (
          <Empty title="Nada por aqui" hint="As faturas aparecerão aqui." />
        ) : (
          <ul className="divide-y divide-border">
            {lista.map((f) => (
              <FaturaRow key={f.id} f={f} />
            ))}
          </ul>
        )}
      </section>

      <div className="mt-4 flex items-start gap-3 rounded-[16px] bg-tax-bg px-4 py-3.5 text-sm text-tax2">
        <FileText size={18} className="mt-0.5 shrink-0" />
        <p>
          {aba === "receber"
            ? "Cada recebimento é conciliado com a NF-e e o IBS/CBS da nota é separado no ato — você recebe o líquido e a apuração já sai pronta para conferir."
            : "Toda compra de insumo com nota gera crédito de IBS/CBS, que abate o imposto das suas vendas na apuração."}
        </p>
      </div>
    </div>
  );
}

function NovaCobranca({ onFechar }: { onFechar: () => void }) {
  const qc = useQueryClient();
  const [valorStr, setValorStr] = useState("");
  const [descricao, setDescricao] = useState("");
  const [vencimento, setVencimento] = useState("");
  const [parcelas, setParcelas] = useState(1);
  const [comNota, setComNota] = useState(true);
  const [chave, setChave] = useState("");
  const [cbsStr, setCbsStr] = useState("");
  const [ibsStr, setIbsStr] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [criadas, setCriadas] = useState<Cobranca[] | null>(null);
  const [copiado, setCopiado] = useState(false);

  const mut = useMutation({
    mutationFn: criarCobranca,
    onSuccess: (cs) => {
      setCriadas(cs);
      void qc.invalidateQueries({ queryKey: ["faturas"] });
    },
    onError: (e: Error) => setErro(e.message),
  });

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const valor = parseValor(valorStr);
    if (!(valor > 0)) return setErro("Informe o valor.");
    if (parcelas > 1 && !vencimento) return setErro("Cobrança parcelada precisa de vencimento.");
    let nota: { chave: string; cbs: number; ibs: number } | undefined;
    if (comNota) {
      const c = chave.replace(/\D/g, "");
      if (c.length !== 44) return setErro("A chave de acesso da nota tem 44 dígitos.");
      const cbs = parseValor(cbsStr || "0");
      const ibs = parseValor(ibsStr || "0");
      if (!(cbs >= 0) || !(ibs >= 0)) return setErro("Informe CBS e IBS como estão na nota.");
      nota = { chave: c, cbs, ibs };
    }
    mut.mutate({
      valor,
      parcelas,
      ...(descricao ? { descricao } : {}),
      ...(vencimento ? { vencimento } : {}),
      ...(nota ? { nota_fiscal: nota } : {}),
    });
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* sem permissão de clipboard: o texto continua visível para copiar à mão */
    }
  }

  if (criadas) {
    const primeira = criadas[0];
    return (
      <section className="surface enter mt-5 space-y-4 p-5">
        <h2 className="text-lg text-ink">
          {criadas.length > 1 ? `${criadas.length} parcelas criadas` : "Cobrança criada"}
        </h2>
        {primeira && (
          <>
            <p className="text-sm text-mut2">
              {primeira.vai_reter_imposto
                ? `No pagamento, ${fmtBRL(criadas.reduce((a, c) => a + c.cbs + c.ibs, 0))} de CBS/IBS da nota vão direto ao Fisco e você recebe o líquido.`
                : "Sem retenção de imposto nesta cobrança."}
            </p>
            <div>
              <p className="text-xs text-mut3">
                Pix copia e cola{criadas.length > 1 ? " (1ª parcela)" : ""}
              </p>
              <div className="mt-1 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-[10px] bg-tint px-3 py-2 text-xs">
                  {primeira.pix_copia_e_cola}
                </code>
                <button
                  className="btn btn-ghost h-9 gap-1 px-3 text-sm"
                  onClick={() => void copiar(primeira.pix_copia_e_cola)}
                >
                  <Copy size={14} /> {copiado ? "Copiado" : "Copiar"}
                </button>
              </div>
              <p className="mt-1 text-[11px] text-mut3">
                Código de demonstração: a emissão de Pix e boleto registrados depende da integração
                com o SPI.
              </p>
            </div>
          </>
        )}
        <button className="btn btn-ink w-full" onClick={onFechar}>
          Concluir
        </button>
      </section>
    );
  }

  return (
    <form onSubmit={enviar} className="surface enter mt-5 space-y-4 p-5">
      <h2 className="text-lg text-ink">Nova cobrança</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valor (R$)" id="cob-valor">
          <input
            id="cob-valor"
            inputMode="decimal"
            className="field tabular"
            value={valorStr}
            onChange={(e) => setValorStr(e.target.value)}
            placeholder="0,00"
          />
        </Field>
        <Field label="Parcelas" id="cob-parcelas">
          <select
            id="cob-parcelas"
            className="field"
            value={parcelas}
            onChange={(e) => setParcelas(Number(e.target.value))}
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n === 1 ? "À vista" : `${n}x`}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Descrição" id="cob-desc">
        <input
          id="cob-desc"
          className="field"
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Ex.: Pedido 4512 — Scania"
        />
      </Field>
      <Field label="Vencimento" id="cob-venc">
        <input
          id="cob-venc"
          type="date"
          className="field"
          value={vencimento}
          onChange={(e) => setVencimento(e.target.value)}
        />
      </Field>

      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={comNota} onChange={(e) => setComNota(e.target.checked)} />
        Vincular nota fiscal (o imposto da nota é separado no pagamento)
      </label>
      {comNota && (
        <div className="space-y-4 rounded-[16px] border border-line2 p-4">
          <Field
            label="Chave de acesso da NF-e"
            id="cob-chave"
            hint="44 dígitos. Conferimos o dígito e o CNPJ do emissor."
          >
            <input
              id="cob-chave"
              inputMode="numeric"
              className="field tabular"
              value={chave}
              onChange={(e) => setChave(e.target.value)}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="CBS da nota (R$)" id="cob-cbs">
              <input
                id="cob-cbs"
                inputMode="decimal"
                className="field tabular"
                value={cbsStr}
                onChange={(e) => setCbsStr(e.target.value)}
                placeholder="0,00"
              />
            </Field>
            <Field label="IBS da nota (R$)" id="cob-ibs">
              <input
                id="cob-ibs"
                inputMode="decimal"
                className="field tabular"
                value={ibsStr}
                onChange={(e) => setIbsStr(e.target.value)}
                placeholder="0,00"
              />
            </Field>
          </div>
        </div>
      )}
      {erro && <ErrorBox>{erro}</ErrorBox>}
      <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
        <button type="button" className="btn btn-ghost" onClick={onFechar}>
          Cancelar
        </button>
        <button className="btn btn-ink" disabled={mut.isPending}>
          {mut.isPending ? "Criando…" : "Criar cobrança"}
        </button>
      </div>
    </form>
  );
}
