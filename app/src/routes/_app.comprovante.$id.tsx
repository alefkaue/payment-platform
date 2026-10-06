import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { transacaoPorId } from "@/lib/api";
import { fmtBRL, fmtData, fmtId } from "@/lib/format";
import type { CategoriaTx } from "@/lib/types";
import { ErrorBox, SplitBar, ValueRow } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/comprovante/$id")({
  head: () => ({
    meta: [
      { title: "Comprovante — PayFlow" },
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
  sistema: "PayFlow",
};

function Comprovante() {
  const { id } = Route.useParams();
  const q = useQuery({ queryKey: ["tx", id], queryFn: () => transacaoPorId(Number(id)) });

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
        <SplitBar liquido={t.liquido} imposto={t.cbs + t.ibs} />
        <div className="mt-3 divide-y divide-border">
          <ValueRow label="Você pagou" value={t.valor_bruto} />
          {t.aplicou_split && <ValueRow label="CBS da nota → Fisco" value={t.cbs} tax />}
          {t.aplicou_split && <ValueRow label="IBS da nota → Fisco" value={t.ibs} tax />}
          <ValueRow
            label={t.aplicou_split ? "Destino recebe (líquido)" : "Destino recebe"}
            value={t.liquido}
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

      <Link to="/inicio" className="btn btn-ink mt-6 w-full">
        Voltar ao início
      </Link>
    </div>
  );
}
