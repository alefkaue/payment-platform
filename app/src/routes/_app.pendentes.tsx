import { BotaoFinanceiro } from "@/lib/mobile";
import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, Clock, KeyRound, RotateCcw, TriangleAlert, X } from "lucide-react";
import {
  aprovacaoPedeTotp,
  decidirPendente,
  pendentes,
  podeRepetirFolha,
  repeticaoPedeTotp,
  repetirPendente,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, fmtData } from "@/lib/format";
import type { ConfirmacaoPagamento, OperacaoPendente } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { ConfirmarPagamento } from "@/components/payflow/confirmar-pagamento";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/pendentes")({
  head: () => ({ meta: [{ title: "Aprovações — Astro" }] }),
  component: Pendentes,
});

function Pendentes() {
  const { conta } = useAuth();
  const q = useQuery({ queryKey: ["pendentes", conta?.numero], queryFn: pendentes });

  if (conta && conta.tipo !== "PJ") return <Navigate to="/inicio" replace />;

  const aguardando = q.data?.filter((o) => o.status === "aguardando") ?? [];
  const decididas = q.data?.filter((o) => o.status !== "aguardando") ?? [];
  const podeAprovar = conta?.papel === "admin" || conta?.papel === "aprovador";

  return (
    <div className="enter">
      <PageTitle sub="Operações acima da alçada de quem lançou e mudanças de acesso, aguardando outra pessoa aprovar.">
        Aprovações pendentes
      </PageTitle>

      {!podeAprovar && (
        <p className="mb-5 rounded-[16px] bg-tint px-4 py-3 text-sm text-mut2">
          Seu papel não aprova operações. Apenas administradores e aprovadores decidem.
        </p>
      )}

      {q.isLoading ? (
        <div className="surface px-5 py-2">
          <TxSkeleton n={3} />
        </div>
      ) : q.isError ? (
        <ErrorBox>Não foi possível carregar as aprovações.</ErrorBox>
      ) : !aguardando.length && !decididas.length ? (
        <div className="surface">
          <Empty title="Nada para aprovar" hint="Operações acima da alçada aparecem aqui." />
        </div>
      ) : (
        <div className="space-y-4">
          {aguardando.map((o) => (
            <Card key={o.id} o={o} podeAprovar={podeAprovar} />
          ))}
          {decididas.length > 0 && (
            <>
              <h2 className="pt-2 text-sm font-semibold uppercase tracking-wide text-mut3">
                Decididas
              </h2>
              {decididas.map((o) => (
                <Card key={o.id} o={o} podeAprovar={podeAprovar} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Card({ o, podeAprovar }: { o: OperacaoPendente; podeAprovar: boolean }) {
  const qc = useQueryClient();
  const [confirmando, setConfirmando] = useState(false);
  const mut = useMutation({
    mutationFn: ({
      aprovar,
      confirmacao,
    }: {
      aprovar: boolean;
      confirmacao?: ConfirmacaoPagamento;
    }) => decidirPendente(o.id, aprovar, confirmacao),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pendentes"] });
      void qc.invalidateQueries({ queryKey: ["nao-lidas"] });
      void qc.invalidateQueries({ queryKey: ["equipe"] });
      void qc.invalidateQueries({ queryKey: ["conta"] });
    },
  });
  const decidida = o.status !== "aguardando";
  const necessarias = o.aprovacoes_necessarias ?? 1;
  const feitas = o.aprovadores?.length ?? 0;

  return (
    <section className={cn("surface p-5", decidida && "opacity-80")}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-semibold text-ink">{o.contraparte}</p>
          <p className="text-sm text-mut2">{o.descricao}</p>
          <p className="mt-1 text-xs text-mut3">
            Lançado por {o.criado_por} · {fmtData(o.criado_em)}
          </p>
        </div>
        <p className="tabular shrink-0 text-xl font-semibold text-ink">{fmtBRL(o.valor)}</p>
      </div>

      {o.status === "aguardando" ? (
        <>
          <div className="mt-3 flex items-center gap-1.5 text-xs font-medium text-tax2">
            <Clock size={13} />
            {necessarias > 1
              ? `${feitas} de ${necessarias} aprovações${feitas ? ` (${o.aprovadores!.join(", ")})` : ""}`
              : "Aguardando 2º aprovador"}
          </div>
          {o.desligados?.length ? (
            <p className="mt-3 flex items-start gap-1.5 rounded-[12px] bg-err-bg px-3 py-2 text-sm text-err">
              <TriangleAlert size={15} className="mt-0.5 shrink-0" />
              <span>
                Desligado(s) depois do lançamento: {o.desligados.join(", ")}. Não recebe(m) por esta
                folha, mesmo com a aprovação.
              </span>
            </p>
          ) : null}
          {podeAprovar && (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                className="btn btn-ghost gap-2 text-err"
                disabled={mut.isPending}
                onClick={() => mut.mutate({ aprovar: false })}
              >
                <X size={18} /> Recusar
              </button>
              <BotaoFinanceiro
                className="btn btn-ink gap-2"
                disabled={mut.isPending}
                onClick={() => {
                  mut.reset();
                  setConfirmando(true);
                }}
              >
                <KeyRound size={18} /> {mut.isPending ? "Enviando…" : "Aprovar"}
              </BotaoFinanceiro>
            </div>
          )}
          {mut.isError && !confirmando && (
            <div className="mt-3">
              <ErrorBox>{(mut.error as Error).message}</ErrorBox>
            </div>
          )}
          {mut.data?.mensagem && <p className="mt-3 text-sm text-mut2">{mut.data.mensagem}</p>}
          {confirmando && (
            <ConfirmarPagamento
              valor={o.tipo === "acesso" ? undefined : o.valor}
              pedeTotp={aprovacaoPedeTotp(o)}
              titulo="Confirme a aprovação"
              acao="Aprovar"
              onClose={() => setConfirmando(false)}
              onConfirmar={async (confirmacao) => {
                await mut.mutateAsync({ aprovar: true, confirmacao });
                setConfirmando(false);
              }}
            />
          )}
        </>
      ) : (
        <Desfecho o={o} podeRepetir={podeAprovar && podeRepetirFolha(o)} />
      )}
    </section>
  );
}

type Tom = "pos" | "aviso" | "erro" | "neutro";
const TONS: Record<Tom, string> = {
  pos: "bg-[color-mix(in_oklab,var(--pos)_14%,transparent)] text-pos",
  aviso: "bg-tint text-tax2",
  erro: "bg-err-bg text-err",
  neutro: "bg-tint text-mut2",
};

/** Cada estado com o seu nome: recusar não é falhar, nem vencer o prazo. */
function selo(o: OperacaoPendente): { texto: string; tom: Tom; Icone: typeof Check } {
  const ex = o.execucao;
  switch (o.status) {
    case "aprovada":
      return ex?.parcial
        ? {
            texto: `Paga em parte: ${ex.executados} de ${ex.itens}`,
            tom: "aviso",
            Icone: TriangleAlert,
          }
        : { texto: "Aprovada", tom: "pos", Icone: Check };
    case "falhou":
      return { texto: "Aprovada, mas não executada", tom: "erro", Icone: TriangleAlert };
    case "executando":
      return { texto: "Em execução", tom: "aviso", Icone: Clock };
    case "expirada":
      return { texto: "Expirada sem decisão", tom: "neutro", Icone: Clock };
    case "cancelada":
      return { texto: "Cancelada", tom: "neutro", Icone: X };
    default:
      return { texto: "Recusada", tom: "erro", Icone: X };
  }
}

function Desfecho({ o, podeRepetir }: { o: OperacaoPendente; podeRepetir: boolean }) {
  const qc = useQueryClient();
  const [confirmando, setConfirmando] = useState(false);
  const mut = useMutation({
    mutationFn: (confirmacao: ConfirmacaoPagamento) => repetirPendente(o.id, confirmacao),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["pendentes"] });
      void qc.invalidateQueries({ queryKey: ["conta"] });
    },
  });
  const { texto, tom, Icone } = selo(o);
  const falhas = o.execucao?.resultados.filter((i) => i.situacao === "erro") ?? [];
  const faltando = falhas.length;

  return (
    <>
      <div
        className={cn(
          "mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
          TONS[tom],
        )}
      >
        <Icone size={13} />
        {texto}
      </div>
      {o.execucao && (
        <p className="mt-2 text-sm text-mut2">
          {o.execucao.executados} de {o.execucao.itens} salário(s) pago(s).
        </p>
      )}
      {o.erro && !o.execucao && <p className="mt-2 text-sm text-err">{o.erro}</p>}
      {faltando > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {falhas.map((i) => (
            <li key={i.funcionario_id} className="text-err">
              <span className="font-medium">{i.nome}</span>: {i.erro ?? "não pago"}
            </li>
          ))}
        </ul>
      )}
      {podeRepetir && (
        <BotaoFinanceiro
          className="btn btn-ghost mt-4 w-full gap-2"
          disabled={mut.isPending}
          onClick={() => {
            mut.reset();
            setConfirmando(true);
          }}
        >
          <RotateCcw size={16} />
          {mut.isPending ? "Enviando…" : `Pagar os ${faltando} que faltam`}
        </BotaoFinanceiro>
      )}
      {mut.isError && !confirmando && (
        <div className="mt-3">
          <ErrorBox>{(mut.error as Error).message}</ErrorBox>
        </div>
      )}
      {confirmando && (
        <ConfirmarPagamento
          pedeTotp={repeticaoPedeTotp(o)}
          titulo="Confirme o pagamento dos que faltam"
          acao="Pagar"
          onClose={() => setConfirmando(false)}
          onConfirmar={async (confirmacao) => {
            await mut.mutateAsync(confirmacao);
            setConfirmando(false);
          }}
        />
      )}
    </>
  );
}
