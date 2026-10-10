import { useFecharAoVoltar, BotaoFinanceiro } from "@/lib/mobile";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, UserPlus } from "lucide-react";
import { cadastrarFuncionario, funcionarios, pagarFolha, removerFuncionario } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, iniciais } from "@/lib/format";
import { num } from "@/lib/http";
import { centavosFolha, decimalFolha, totalFolha } from "@/lib/folha";
import type { FolhaItem, ProvaBiometrica, ResultadoFolha } from "@/lib/types";
import { Empty, ErrorBox, Field, PageTitle } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";
import { criarIntencaoPagamento } from "@/lib/intencao-pagamento";

export const Route = createFileRoute("/_app/folha")({
  head: () => ({ meta: [{ title: "Folha de pagamento — Astro" }] }),
  component: Folha,
});

function Folha() {
  const { conta } = useAuth();
  // Trocar de empresa também descarta o formulário e o resultado anterior.
  return <FolhaConta key={conta?.carteira_id} />;
}

function FolhaConta() {
  const { conta } = useAuth();
  const qc = useQueryClient();
  const pj = conta?.tipo === "PJ";
  const admin = pj && conta.papel === "admin";
  const podePagar = pj && ["admin", "aprovador", "operador"].includes(conta.papel ?? "");
  const q = useQuery({
    queryKey: ["funcionarios", conta?.carteira_id],
    queryFn: funcionarios,
    enabled: podePagar,
  });
  const [nome, setNome] = useState("");
  const [cpf, setCpf] = useState("");
  const [cargo, setCargo] = useState("");
  const [salario, setSalario] = useState("");
  const [cadastroAberto, setCadastroAberto] = useState(false);
  useFecharAoVoltar(cadastroAberto, () => setCadastroAberto(false));
  const [remover, setRemover] = useState<number | null>(null);
  useFecharAoVoltar(remover !== null, () => setRemover(null), 10);
  const [selecionados, setSelecionados] = useState<Record<number, string>>({});
  const [descricao, setDescricao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [rosto, setRosto] = useState(false);
  const [pedido, setPedido] = useState<FolhaItem[]>([]);
  const [resultado, setResultado] = useState<ResultadoFolha | null>(null);
  const [intencao] = useState(criarIntencaoPagamento);
  const [chave, setChave] = useState("");
  const cadastrar = useMutation({
    mutationFn: cadastrarFuncionario,
    onSuccess: () => {
      setNome("");
      setCpf("");
      setCargo("");
      setSalario("");
      setCadastroAberto(false);
      void qc.invalidateQueries({ queryKey: ["funcionarios"] });
    },
  });
  const desligar = useMutation({
    mutationFn: removerFuncionario,
    onSuccess: (_, id) => {
      setRemover(null);
      setSelecionados((atual) => {
        const copia = { ...atual };
        delete copia[id];
        return copia;
      });
      void qc.invalidateQueries({ queryKey: ["funcionarios"] });
    },
  });
  const pagar = useMutation({
    mutationFn: ({
      itens,
      prova,
      chave,
    }: {
      itens: FolhaItem[];
      prova?: ProvaBiometrica;
      chave: string;
    }) => pagarFolha(itens, descricao.trim(), prova, chave),
    onSuccess: (r) => {
      setResultado(r);
      if ("pendente" in r || r.resultados.every((item) => item.situacao === "pago")) {
        intencao.concluir();
        setSelecionados({});
      }
      void qc.invalidateQueries();
    },
  });
  const ocupada = cadastrar.isPending || desligar.isPending || pagar.isPending || rosto;
  const valores = Object.values(selecionados);
  let total = "0.00";
  let valido = valores.length > 0;
  try {
    total = totalFolha(valores);
    valido = valido && valores.every((v) => centavosFolha(v) > 0n);
  } catch {
    valido = false;
  }
  const acimaAlcada =
    conta?.alcada != null && centavosFolha(total) > centavosFolha(conta.alcada.toFixed(2));
  const conjunta = conta?.porte === "GRANDE" && centavosFolha(total) >= 25000000n;

  if (!pj)
    return (
      <>
        <PageTitle>Folha de pagamento</PageTitle>
        <Empty
          title="Disponível na conta da empresa"
          hint="Troque para uma conta PJ para acessar a folha."
        />
      </>
    );
  if (!podePagar)
    return (
      <>
        <PageTitle>Folha de pagamento</PageTitle>
        <section className="surface p-5">
          <p className="text-sm text-mut2">
            Seu acesso é só de consulta. A lista de funcionários exige acesso de administrador,
            aprovador ou operador.
          </p>
        </section>
      </>
    );

  function confirmar() {
    setErro(null);
    pagar.reset();
    setResultado(null);
    if (!valido) {
      setErro("Selecione funcionários e informe valores positivos com até duas casas decimais.");
      return;
    }
    const itens = Object.entries(selecionados).map(([id, valor]) => ({
      funcionario_id: Number(id),
      valor: decimalFolha(centavosFolha(valor)),
    }));
    setPedido(itens);
    const chave = intencao.preparar(JSON.stringify([conta?.carteira_id, itens]));
    setChave(chave);
    if (centavosFolha(total) > 50000n && !acimaAlcada && !conjunta) setRosto(true);
    else pagar.mutate({ itens, chave });
  }

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Salários enviados à conta pessoal de cada funcionário, pelo CPF.">
        Folha de pagamento
      </PageTitle>
      <section className="surface space-y-4 p-5">
        <h2 className="text-lg text-ink">Funcionários</h2>
        {q.isPending && (
          <p role="status" className="text-sm text-mut3">
            Carregando funcionários…
          </p>
        )}
        {q.isError && (
          <>
            <ErrorBox>{q.error.message}</ErrorBox>
            <button className="btn btn-ghost" onClick={() => void q.refetch()}>
              Tentar novamente
            </button>
          </>
        )}
        {q.data?.length === 0 && <Empty title="Nenhum funcionário cadastrado" />}
        <ul className="divide-y divide-line2">
          {q.data?.map((f) => (
            <li key={f.id} className="space-y-3 py-3.5">
              <button
                type="button"
                className="flex w-full items-center gap-3 text-left"
                disabled={ocupada}
                aria-pressed={selecionados[f.id] !== undefined}
                onClick={() => {
                  setResultado(null);
                  pagar.reset();
                  setSelecionados((atual) => {
                    const copia = { ...atual };
                    if (atual[f.id] === undefined) copia[f.id] = f.salario ?? "";
                    else delete copia[f.id];
                    return copia;
                  });
                }}
              >
                <span
                  aria-hidden="true"
                  className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-sm font-semibold text-ink"
                >
                  {iniciais(f.nome)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-ink">{f.nome}</span>
                  <span className="block truncate text-xs text-mut3">
                    {f.cargo || "Cargo não informado"} · {f.cpf}
                  </span>
                </span>
                <span
                  aria-hidden="true"
                  className={`grid h-5 w-5 shrink-0 place-items-center rounded-full ${selecionados[f.id] !== undefined ? "bg-ink text-white" : "border border-line2"}`}
                >
                  {selecionados[f.id] !== undefined && <Check size={14} />}
                </span>
                <span className="tabular shrink-0 text-right text-sm text-mut2">
                  {f.salario == null ? "Não informado" : fmtBRL(num(f.salario))}
                </span>
              </button>
              {selecionados[f.id] !== undefined && (
                <Field id={`valor-${f.id}`} label={`Valor para ${f.nome} (R$)`}>
                  <input
                    autoComplete="off"
                    id={`valor-${f.id}`}
                    className="field tabular"
                    inputMode="decimal"
                    disabled={ocupada}
                    value={selecionados[f.id]}
                    onChange={(e) =>
                      setSelecionados((atual) => ({ ...atual, [f.id]: e.target.value }))
                    }
                  />
                </Field>
              )}
              {admin &&
                (remover === f.id ? (
                  <div className="space-y-2 rounded-[14px] bg-tint p-3">
                    <p className="text-sm text-mut2">Remover {f.nome} dos funcionários?</p>
                    <BotaoFinanceiro
                      className="btn btn-ink"
                      disabled={ocupada}
                      onClick={() => desligar.mutate(f.id)}
                    >
                      Confirmar remoção
                    </BotaoFinanceiro>
                    <button
                      className="btn btn-ghost"
                      disabled={ocupada}
                      onClick={() => setRemover(null)}
                    >
                      Cancelar
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-x-4 gap-y-1 pl-[52px]">
                    <button
                      type="button"
                      className="text-xs font-semibold text-err underline underline-offset-4"
                      disabled={ocupada}
                      onClick={() => {
                        desligar.reset();
                        setRemover(f.id);
                      }}
                    >
                      Remover
                    </button>
                  </div>
                ))}
            </li>
          ))}
        </ul>
        {desligar.isError && <ErrorBox>{desligar.error.message}</ErrorBox>}
      </section>
      <section className="surface space-y-4 p-5">
        <h2 className="text-lg text-ink">Pagar folha</h2>
        <p className="tabular font-semibold text-ink">Total: {fmtBRL(num(total))}</p>
        <Field id="folha-descricao" label="Descrição (opcional)">
          <input
            id="folha-descricao"
            className="field"
            maxLength={100}
            value={descricao}
            disabled={ocupada}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </Field>
        <p className="text-sm text-mut3">
          Pagamentos seguem sua alçada diária e a assinatura conjunta. Se precisar de aprovação, o
          saldo não é debitado agora.
        </p>
        {erro && <ErrorBox>{erro}</ErrorBox>}
        {pagar.isError && <ErrorBox>{pagar.error.message}</ErrorBox>}
        <BotaoFinanceiro
          className="btn btn-ink w-full"
          disabled={ocupada || !valido}
          onClick={confirmar}
        >
          {pagar.isPending
            ? "Enviando…"
            : acimaAlcada || conjunta
              ? "Enviar para aprovação"
              : "Pagar folha"}
        </BotaoFinanceiro>
        {resultado &&
          ("pendente" in resultado ? (
            <p role="status" className="text-sm text-pending">
              Enviada para aprovação. Operação #{resultado.pendente.id}.
            </p>
          ) : (
            <div role="status" className="space-y-2">
              <p className="text-sm text-ink">
                {resultado.resultados.every((r) => r.situacao === "pago")
                  ? "Folha paga"
                  : "Folha com pagamentos não concluídos"}
              </p>
              {resultado.resultados
                .filter((r) => r.situacao === "erro")
                .map((r) => (
                  <ErrorBox key={r.funcionario_id}>
                    {q.data?.find((f) => f.id === r.funcionario_id)?.nome ??
                      `Funcionário #${r.funcionario_id}`}
                    : {r.erro ?? "Pagamento não concluído."}
                  </ErrorBox>
                ))}
            </div>
          ))}
      </section>
      {admin && (
        <section className="surface p-5">
          {cadastroAberto ? (
            <>
              <h2 className="mb-4 text-lg text-ink">Cadastrar funcionário</h2>
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  setErro(null);
                  try {
                    cadastrar.mutate({
                      nome: nome.trim(),
                      cpf,
                      ...(cargo.trim() ? { cargo: cargo.trim() } : {}),
                      ...(salario.trim() ? { salario: decimalFolha(centavosFolha(salario)) } : {}),
                    });
                  } catch (e) {
                    setErro((e as Error).message);
                  }
                }}
              >
                <Field id="func-nome" label="Nome">
                  <input
                    autoComplete="name"
                    id="func-nome"
                    className="field"
                    required
                    minLength={3}
                    maxLength={120}
                    value={nome}
                    disabled={ocupada}
                    onChange={(e) => setNome(e.target.value)}
                  />
                </Field>
                <Field id="func-cpf" label="CPF">
                  <input
                    autoComplete="off"
                    id="func-cpf"
                    className="field"
                    inputMode="numeric"
                    required
                    minLength={11}
                    maxLength={14}
                    value={cpf}
                    disabled={ocupada}
                    onChange={(e) => setCpf(e.target.value)}
                  />
                </Field>
                <Field id="func-cargo" label="Cargo (opcional)">
                  <input
                    id="func-cargo"
                    className="field"
                    maxLength={80}
                    value={cargo}
                    disabled={ocupada}
                    onChange={(e) => setCargo(e.target.value)}
                  />
                </Field>
                <Field id="func-salario" label="Salário (R$, opcional)">
                  <input
                    autoComplete="off"
                    id="func-salario"
                    className="field"
                    inputMode="decimal"
                    value={salario}
                    disabled={ocupada}
                    onChange={(e) => setSalario(e.target.value)}
                  />
                </Field>
                {cadastrar.isError && <ErrorBox>{cadastrar.error.message}</ErrorBox>}
                <BotaoFinanceiro className="btn btn-ink w-full" disabled={ocupada}>
                  {cadastrar.isPending ? "Cadastrando…" : "Cadastrar"}
                </BotaoFinanceiro>
                <button
                  type="button"
                  className="btn btn-ghost w-full"
                  disabled={ocupada}
                  onClick={() => {
                    setCadastroAberto(false);
                    cadastrar.reset();
                    setErro(null);
                    setNome("");
                    setCpf("");
                    setCargo("");
                    setSalario("");
                  }}
                >
                  Cancelar
                </button>
              </form>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-ghost w-full gap-2"
              disabled={ocupada}
              aria-expanded={cadastroAberto}
              onClick={() => setCadastroAberto(true)}
            >
              <UserPlus size={18} aria-hidden="true" /> Cadastrar funcionário
            </button>
          )}
        </section>
      )}
      {rosto && (
        <LivenessCheck
          onClose={() => setRosto(false)}
          onSuccess={(prova) => {
            setRosto(false);
            pagar.mutate({ itens: pedido, prova, chave });
          }}
        />
      )}
    </div>
  );
}
