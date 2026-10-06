import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Copy, FileText, Plus } from "lucide-react";
import { criarCobranca, listarCobrancas, listarFaturas, MODO_API } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData, parseValor } from "@/lib/format";
import type { Cobranca } from "@/lib/types";
import { Empty, ErrorBox, Field, MetricTile, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { FaturaRow } from "./_app.inicio";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/contas")({
  head: () => ({ meta: [{ title: "Cobranças — PayFlow" }] }),
  component: Contas,
});

const STATUS: Record<Cobranca["status"], string> = {
  aberta: "Aberta",
  paga: "Paga",
  cancelada: "Cancelada",
  estornada: "Estornada",
};

/**
 * Cobranças da empresa. É aqui que o split acontece: a cobrança leva a nota
 * fiscal (chave de 44 dígitos + CBS e IBS destacados nela) e, quando o cliente
 * paga, o banco separa esse imposto e a empresa recebe o líquido.
 */
function Contas() {
  const { conta } = useAuth();
  const [aba, setAba] = useState<"cobrancas" | "pagar">("cobrancas");
  const [nova, setNova] = useState(false);
  const cobs = useQuery({ queryKey: ["cobrancas", conta?.numero], queryFn: listarCobrancas });
  const pagar = useQuery({
    queryKey: ["faturas-pagar", conta?.numero],
    queryFn: () => listarFaturas("pagar"),
  });

  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  const lista = cobs.data ?? [];
  const abertas = lista.filter((c) => c.status === "aberta");
  const pagas = lista.filter((c) => c.status === "paga");
  const totAberto = abertas.reduce((a, c) => a + c.valor, 0);
  const impostoPago = pagas
    .filter((c) => c.vai_reter_imposto)
    .reduce((a, c) => a + c.cbs + c.ibs, 0);

  return (
    <div className="enter">
      <PageTitle sub="Cobre com a nota fiscal: no pagamento, a CBS e o IBS da nota são separados e você recebe o líquido.">
        Cobranças
      </PageTitle>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricTile label="Em aberto" value={fmtBRL(totAberto)} />
        <MetricTile label="Recebidas" value={String(pagas.length)} tone="pos" />
        <MetricTile
          label="Imposto separado"
          value={fmtBRL(impostoPago)}
          tone="tax"
          hint="das notas pagas"
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
        {(["cobrancas", "pagar"] as const).map((d) => (
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
            {d === "cobrancas" ? "Cobranças emitidas" : "A pagar"}
          </button>
        ))}
      </div>

      <section className="surface mt-4 px-5 py-2">
        {aba === "cobrancas" ? (
          cobs.isLoading ? (
            <TxSkeleton n={3} />
          ) : cobs.isError ? (
            <div className="py-4">
              <ErrorBox>Não foi possível carregar as cobranças.</ErrorBox>
            </div>
          ) : !lista.length ? (
            <Empty title="Nenhuma cobrança ainda" hint="Crie a primeira com o botão acima." />
          ) : (
            <ul className="divide-y divide-border">
              {lista.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-4 py-3.5">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{c.descricao || "Cobrança"}</p>
                    <p className="truncate text-xs text-mut3">
                      {STATUS[c.status]}
                      {c.vencimento ? ` · vence ${fmtData(c.vencimento).split(",")[0]}` : ""}
                      {c.nfe_chave ? " · com NF-e" : " · sem nota"}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="tabular font-semibold text-ink">{fmtBRL(c.valor)}</p>
                    {c.vai_reter_imposto && (
                      <p className="text-[11px] text-tax">
                        imposto da nota {fmtBRL(c.cbs + c.ibs)}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : pagar.isLoading ? (
          <TxSkeleton n={3} />
        ) : !pagar.data?.length ? (
          <Empty
            title="Nada a pagar por aqui"
            hint={
              MODO_API
                ? "Contas a pagar (DDA) ainda não estão ligadas ao banco."
                : "As faturas aparecerão aqui."
            }
          />
        ) : (
          <ul className="divide-y divide-border">
            {pagar.data.map((f) => (
              <FaturaRow key={f.id} f={f} />
            ))}
          </ul>
        )}
      </section>

      <div className="mt-4 flex items-start gap-3 rounded-[16px] bg-tax-bg px-4 py-3.5 text-sm text-tax2">
        <FileText size={18} className="mt-0.5 shrink-0" />
        <p>
          {aba === "cobrancas"
            ? "Só cobranças com nota têm split, e só para empresas do regime regular (Simples e MEI recolhem do jeito de sempre). Transferências comuns nunca têm imposto retido."
            : "Compras com nota geram crédito de IBS/CBS na sua apuração. Quem abate é o Fisco; aqui você acompanha a estimativa."}
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
      void qc.invalidateQueries({ queryKey: ["cobrancas"] });
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
