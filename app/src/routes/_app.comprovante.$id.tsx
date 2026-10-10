import { useFecharAoVoltar } from "@/lib/mobile";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check } from "lucide-react";
import { ApiError, apuracaoPJ, contestar, listarCobrancas, transacaoPorId } from "@/lib/api";
import { SplitAviso } from "@/components/payflow/split-aviso";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData, fmtId } from "@/lib/format";
import type { CategoriaTx, Transacao } from "@/lib/types";
import { ErrorBox, Field, SplitBar, ValueRow } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/comprovante/$id")({
  head: () => ({
    meta: [
      { title: "Comprovante — Astro" },
      { name: "description", content: "Comprovante com detalhamento do split." },
    ],
  }),
  component: Comprovante,
});

const TITULO: Record<CategoriaTx, string> = {
  transferencia: "Transferência enviada",
  compra: "Compra confirmada",
  viagem: "Passagem emitida",
  deposito: "Depósito confirmado",
  recebimento: "Pagamento recebido",
  cobranca: "Cobrança paga",
  rendimento: "Rendimento creditado",
  estorno: "Valor devolvido",
};

const AUTH: Record<string, string> = {
  senha: "senha do app",
  selfie: "verificação facial",
  aprovacao: "aprovação de outra pessoa da empresa",
  automatico: "Pix Automático (autorização prévia)",
  sistema: "Astro",
};

function Comprovante() {
  const { id } = Route.useParams();
  const { conta } = useAuth();
  const q = useQuery({
    queryKey: ["tx", conta?.numero, id],
    queryFn: () => transacaoPorId(Number(id)),
  });
  const apuracao = useQuery({
    queryKey: ["apuracao-pj", conta?.numero],
    queryFn: apuracaoPJ,
    enabled: conta?.tipo === "PJ",
  });
  // No informativo a transação tem tributos zerados; o destaque continua na cobrança.
  const cobrancas = useQuery({
    queryKey: ["cobrancas", conta?.numero],
    queryFn: listarCobrancas,
    enabled: conta?.tipo === "PJ" && q.data?.categoria === "recebimento" && !q.data.aplicou_split,
  });

  if (q.isLoading)
    return <div className="mx-auto mt-10 h-64 max-w-md animate-pulse rounded-[22px] bg-card" />;
  if (q.isError || !q.data)
    return (
      <div className="space-y-4">
        <ErrorBox>Comprovante não encontrado.</ErrorBox>
        <Link to="/inicio" className="btn btn-ghost">
          Voltar ao início
        </Link>
      </div>
    );
  const t = q.data;
  const cobranca = cobrancas.data?.find((c) => c.transacao_id === t.id);
  const impostoDestacado = cobranca
    ? cobranca.cbs + cobranca.ibs
    : (t.imposto_nota ?? t.cbs + t.ibs);

  return (
    <div className="enter mx-auto max-w-md text-center">
      <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-tint text-ink">
        <Check size={28} strokeWidth={2.5} />
      </div>
      <h1 className="mt-5 text-2xl text-ink">{TITULO[t.categoria] ?? "Pagamento enviado"}</h1>
      <p className="tabular mt-2 text-5xl font-semibold tracking-display text-ink">
        {fmtBRL(t.valor_bruto)}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        {t.descricao} · {fmtData(t.criado_em)}
      </p>

      <section className="surface mt-8 p-5 text-left md:p-6">
        <SplitAviso fase={t.split_fase ?? apuracao.data?.split_fase} />
        <SplitBar
          liquido={t.aplicou_split ? t.liquido : t.valor_bruto}
          imposto={t.aplicou_split ? t.cbs + t.ibs : 0}
        />
        <div className="mt-3 divide-y divide-border">
          <ValueRow label="Você pagou" value={t.valor_bruto} />
          {t.aplicou_split && (
            <ValueRow label="CBS da nota separado para o Fisco" value={t.cbs} tax />
          )}
          {t.aplicou_split && (
            <ValueRow label="IBS da nota separado para o Fisco" value={t.ibs} tax />
          )}
          {!t.aplicou_split && impostoDestacado > 0 && (
            <p className="py-2 text-sm text-mut2">
              Imposto destacado na nota: {fmtBRL(impostoDestacado)} (não retido em 2026)
            </p>
          )}
          <ValueRow
            label={t.aplicou_split ? "Destino recebe (líquido)" : "Destino recebe"}
            value={t.aplicou_split ? t.liquido : t.valor_bruto}
            strong
          />
        </div>
        {!t.aplicou_split && (
          <p className="mt-2 text-sm text-mut2">
            {t.categoria === "transferencia"
              ? "Transferência não tem retenção de imposto."
              : "Sem retenção de imposto."}
          </p>
        )}
        {t.status === "retida" && (
          <p className="mt-2 rounded-[12px] bg-tax-bg px-3 py-2 text-sm text-tax2">
            Por segurança, o valor fica em análise por até 72h antes de ser liberado ao destino.
          </p>
        )}
        <p className="mt-4 rounded-[12px] bg-tint px-3 py-2 font-mono text-xs text-mut2">
          {fmtId(t.id)} · autorizado por {AUTH[t.auth_metodo] ?? t.auth_metodo}
        </p>
      </section>

      <Contestacao key={`${conta?.numero}:${id}`} transacao={t} />

      <Link to="/inicio" className="btn btn-ink mt-6 w-full">
        Voltar ao início
      </Link>
    </div>
  );
}

function Contestacao({ transacao: t }: { transacao: Transacao }) {
  const { conta } = useAuth();
  const qc = useQueryClient();
  const [aberto, setAberto] = useState(false);
  useFecharAoVoltar(aberto, () => setAberto(false));
  const [motivo, setMotivo] = useState("");
  const [enviada, setEnviada] = useState(false);
  const mut = useMutation({
    mutationFn: () => contestar(t.id, motivo.trim()),
    onSuccess: () => {
      setEnviada(true);
      setAberto(false);
      void qc.invalidateQueries({ queryKey: ["tx"] });
    },
  });
  const jaAberta =
    enviada || t.contestacao_aberta || (mut.error instanceof ApiError && mut.error.status === 409);
  const idade = Date.now() - new Date(t.criado_em).getTime();
  const pode =
    t.origem_carteira_id === conta?.carteira_id &&
    t.status === "concluida" &&
    idade >= 0 &&
    idade <= 80 * 86400000 &&
    (t.categoria === "transferencia" || t.categoria === "cobranca") &&
    (conta.tipo === "PF" || conta.papel === "admin");

  if (jaAberta)
    return (
      <div className="mt-5 space-y-3">
        <p role="status" className="text-sm text-pending">
          Contestação aberta
        </p>
        {mut.error && <ErrorBox>{mut.error.message}</ErrorBox>}
      </div>
    );
  if (!pode) return null;
  return (
    <section className="surface mt-5 p-5 text-left">
      <p className="text-sm text-mut2">
        O valor pode ser devolvido após a análise, e o recebedor fica sabendo da contestação.
      </p>
      {aberto ? (
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (motivo.trim().length >= 5 && !mut.isPending) mut.mutate();
          }}
        >
          <Field label="Motivo" id="contestacao-motivo" hint="Mínimo de 5 caracteres.">
            <textarea
              id="contestacao-motivo"
              className="field"
              rows={3}
              minLength={5}
              maxLength={280}
              required
              value={motivo}
              disabled={mut.isPending}
              onChange={(e) => setMotivo(e.target.value)}
            />
          </Field>
          <p className="text-xs text-mut3">{motivo.length}/280 caracteres</p>
          {mut.error && <ErrorBox>{mut.error.message}</ErrorBox>}
          <div className="grid gap-3">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={mut.isPending}
              onClick={() => {
                setAberto(false);
                mut.reset();
              }}
            >
              Cancelar
            </button>
            <button className="btn btn-ink" disabled={mut.isPending || motivo.trim().length < 5}>
              {mut.isPending ? "Enviando…" : "Enviar contestação"}
            </button>
          </div>
        </form>
      ) : (
        <button className="btn btn-ghost mt-4 w-full" onClick={() => setAberto(true)}>
          Contestar
        </button>
      )}
    </section>
  );
}
