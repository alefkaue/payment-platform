import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ScrollText } from "lucide-react";
import { auditoriaEmpresa } from "@/lib/api";
import { detalheAuditoria, filtrarAuditoria, type TipoAuditoria } from "@/lib/auditoria";
import { useAuth } from "@/lib/auth";
import { fmtData } from "@/lib/format";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/auditoria")({
  head: () => ({ meta: [{ title: "Auditoria — Astro" }] }),
  component: Auditoria,
});

function Auditoria() {
  const { conta } = useAuth();
  const [limite, setLimite] = useState(50);
  const [texto, setTexto] = useState("");
  const [tipo, setTipo] = useState<TipoAuditoria>("Todos");
  const permitido =
    conta?.tipo === "PJ" && (conta.papel === "admin" || conta.papel === "aprovador");
  const trilha = useQuery({
    queryKey: ["auditoria", conta?.id, conta?.papel, limite],
    queryFn: () => auditoriaEmpresa(limite),
    enabled: permitido,
    placeholderData: keepPreviousData,
  });
  const itens = filtrarAuditoria(trilha.data ?? [], texto, tipo);

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Quem fez cada ação e quando ela aconteceu.">Auditoria da empresa</PageTitle>
      {!permitido ? (
        <Empty
          title={conta?.tipo === "PJ" ? "Acesso restrito" : "Só para empresas"}
          hint={
            conta?.tipo === "PJ"
              ? "Só administradores e aprovadores veem a trilha da empresa."
              : "Selecione uma conta PJ para consultar a auditoria."
          }
        />
      ) : (
        <section className="surface p-5">
          <h2 className="flex items-center gap-2 text-lg text-ink">
            <ScrollText size={18} /> Atividade recente
          </h2>
          <label className="mt-4 block text-sm text-ink" htmlFor="busca-auditoria">
            Buscar por ação ou pessoa
          </label>
          <input
            id="busca-auditoria"
            className="field mt-2 w-full"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Descrição ou quem fez"
          />
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Tipo de atividade">
            {(["Todos", "Acessos", "Pagamentos", "Aprovações"] as const).map((opcao) => (
              <button
                key={opcao}
                className={`btn ${tipo === opcao ? "btn-ink" : "btn-ghost"}`}
                aria-pressed={tipo === opcao}
                onClick={() => setTipo(opcao)}
              >
                {opcao}
              </button>
            ))}
          </div>
          {trilha.isError && (
            <div className="mt-3">
              <ErrorBox>{trilha.error.message}</ErrorBox>
            </div>
          )}
          {trilha.isLoading ? (
            <TxSkeleton n={3} />
          ) : !itens.length ? (
            <Empty
              title="Nenhuma atividade encontrada"
              hint="Tente outro filtro ou carregue mais atividades."
            />
          ) : (
            <ul className="mt-3 divide-y divide-line2">
              {itens.map((a) => {
                const detalhe = detalheAuditoria(a.detalhe);
                return (
                  <li key={a.id} className="py-3">
                    <p className="text-sm text-ink">{a.descricao}</p>
                    <p className="break-words text-xs text-mut3">
                      {a.ator} · {fmtData(a.criado_em)} · {a.ip ?? "IP desconhecido"}
                    </p>
                    {detalhe && <p className="text-xs text-mut3">{detalhe}</p>}
                  </li>
                );
              })}
            </ul>
          )}
          {limite < 200 && (
            <button
              className="btn btn-ghost mt-4 w-full"
              disabled={trilha.isFetching}
              onClick={() => setLimite((atual) => Math.min(200, atual + 50))}
            >
              {trilha.isFetching ? "Carregando…" : "Carregar mais"}
            </button>
          )}
          <p className="mt-3 text-xs text-mut3">
            Até {limite} atividades recentes. Os filtros usam a lista carregada.
          </p>
        </section>
      )}
    </div>
  );
}
