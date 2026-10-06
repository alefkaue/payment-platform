import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { comprarProduto, produtoPorId } from "@/lib/api";
import { calcularSplit } from "@/lib/split";
import { fmtBRL } from "@/lib/format";
import { ErrorBox, SelfieCapture, SplitBar, ValueRow } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/loja/$id")({
  head: () => ({ meta: [{ title: "Produto — PayFlow" }] }),
  component: ProdutoDetalhe,
});

function ProdutoDetalhe() {
  const { id } = Route.useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["produto", id], queryFn: () => produtoPorId(Number(id)) });
  const [selfie, setSelfie] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (q.isLoading)
    return <div className="mx-auto mt-6 h-96 max-w-md animate-pulse rounded-[22px] bg-card" />;
  if (q.isError || !q.data)
    return (
      <div className="space-y-4">
        <ErrorBox>Produto não encontrado.</ErrorBox>
        <Link to="/loja" className="btn btn-ghost">
          Voltar à loja
        </Link>
      </div>
    );

  const p = q.data;
  const split = calcularSplit(p.preco, "PJ"); // lojista é sempre PJ
  const precisaSelfie = p.preco > 500;

  async function comprar() {
    setErro(null);
    if (precisaSelfie && !selfie) return setErro("Capture a selfie para compras acima de R$ 500.");
    setLoading(true);
    try {
      const t = await comprarProduto({ produto_id: p.id, selfie: precisaSelfie ? selfie : null });
      qc.invalidateQueries();
      nav({ to: "/comprovante/$id", params: { id: String(t.id) } });
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="enter mx-auto max-w-md">
      <Link
        to="/loja"
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-mut2 hover:text-ink"
      >
        <ArrowLeft size={16} /> Loja
      </Link>

      <div className="surface overflow-hidden">
        <div className="grid aspect-[16/10] place-items-center bg-gradient-to-br from-tint to-tax-bg text-7xl">
          {p.emoji}
        </div>
        <div className="p-5 md:p-6">
          <span className="text-xs font-medium text-mut3">
            {p.categoria} · {p.merchant_nome}
          </span>
          <h1 className="mt-1 text-2xl text-ink">{p.nome}</h1>
          <p className="mt-2 text-muted-foreground">{p.descricao}</p>
          <p className="tabular mt-4 text-3xl font-semibold tracking-display text-ink">
            {fmtBRL(p.preco)}
          </p>

          <div className="mt-6">
            <SplitBar liquido={split.liquido} imposto={split.imposto_total} />
            <div className="mt-3 divide-y divide-border">
              <ValueRow label="Você paga" value={split.valor_bruto} />
              <ValueRow label="CBS → Governo" value={split.cbs} tax />
              <ValueRow label="IBS → Governo" value={split.ibs} tax />
              <ValueRow label={`${p.merchant_nome} recebe`} value={split.liquido} strong />
            </div>
            <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
              Vigência {split.vigencia} · imposto {fmtBRL(split.imposto_total)} retido no ato da
              compra.
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
            {loading ? "Processando…" : `Comprar · ${fmtBRL(p.preco)}`}
          </button>
        </div>
      </div>
    </div>
  );
}
