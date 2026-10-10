import { useFecharAoVoltar } from "@/lib/mobile";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { History, Lock, LockOpen, LogOut, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import {
  bloquearAparelho,
  desbloquearAparelho,
  encerrarOutrasSessoes,
  encerrarSessao,
  meusAparelhos,
  minhaAtividade,
  minhasSessoes,
  removerAparelho,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtData } from "@/lib/format";
import type { Aparelho } from "@/lib/types";
import { Empty, ErrorBox, PageTitle, TxSkeleton } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/_app/seguranca")({
  head: () => ({ meta: [{ title: "Segurança — Astro" }] }),
  component: Seguranca,
});

/** Ação que espera o "sim" da pessoa na própria tela (sem confirm do navegador). */
type Pedido =
  | { tipo: "bloquear" | "remover"; aparelho: Aparelho }
  | { tipo: "encerrar"; sessaoId: string; atual: boolean }
  | { tipo: "encerrar-outras" };

/**
 * Aparelhos, sessões e atividade. É o caminho do "meu celular foi roubado":
 * bloquear o aparelho derruba as sessões dele na hora; desbloquear pede o rosto.
 */
function Seguranca() {
  const qc = useQueryClient();
  const { sair } = useAuth();
  const aparelhos = useQuery({ queryKey: ["seguranca", "aparelhos"], queryFn: meusAparelhos });
  const sessoes = useQuery({ queryKey: ["seguranca", "sessoes"], queryFn: minhasSessoes });
  const atividade = useQuery({ queryKey: ["seguranca", "atividade"], queryFn: minhaAtividade });
  const [pedido, setPedido] = useState<Pedido | null>(null);
  useFecharAoVoltar(pedido, () => setPedido(null), 10);
  const [desbloquear, setDesbloquear] = useState<Aparelho | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const recarregar = () => qc.invalidateQueries({ queryKey: ["seguranca"] });

  async function executar(fn: () => Promise<string | null>, saiDaConta = false) {
    setErro(null);
    setAviso(null);
    setEnviando(true);
    try {
      const msg = await fn();
      setPedido(null);
      // Bloqueou o próprio aparelho ou encerrou a própria sessão: esta sessão acabou.
      if (saiDaConta) return sair();
      setAviso(msg);
      await recarregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  function confirmar() {
    if (!pedido) return;
    if (pedido.tipo === "bloquear")
      void executar(async () => {
        await bloquearAparelho(pedido.aparelho.id);
        return "Aparelho bloqueado. As sessões dele foram encerradas.";
      }, pedido.aparelho.atual);
    else if (pedido.tipo === "remover")
      void executar(async () => {
        await removerAparelho(pedido.aparelho.id);
        return "Aparelho removido.";
      }, pedido.aparelho.atual);
    else if (pedido.tipo === "encerrar")
      void executar(async () => {
        await encerrarSessao(pedido.sessaoId);
        return "Sessão encerrada.";
      }, pedido.atual);
    else
      void executar(async () => {
        const n = await encerrarOutrasSessoes();
        return n === 1 ? "1 sessão encerrada." : `${n} sessões encerradas.`;
      });
  }

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Aparelhos com acesso, sessões abertas e o que aconteceu na sua conta.">
        Segurança
      </PageTitle>

      <div
        role="status"
        className="flex items-start gap-2 rounded-[14px] bg-tint px-4 py-3 text-sm text-ink"
      >
        <ShieldCheck size={16} className="mt-0.5 shrink-0" />
        <span>
          Perdeu o celular? Entre por outro aparelho e bloqueie o perdido aqui: as sessões dele caem
          na hora.
        </span>
      </div>

      {aviso && <p className="text-sm text-pos">{aviso}</p>}
      {erro && <ErrorBox>{erro}</ErrorBox>}

      {pedido && (
        <section className="surface p-5" aria-live="polite">
          <p className="font-medium text-ink">{tituloDoPedido(pedido)}</p>
          <p className="mt-1 text-xs text-mut3">{detalheDoPedido(pedido)}</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button className="btn btn-ghost" disabled={enviando} onClick={() => setPedido(null)}>
              Cancelar
            </button>
            <button className="btn btn-ink" disabled={enviando} onClick={confirmar}>
              {enviando ? "Aguarde…" : "Confirmar"}
            </button>
          </div>
        </section>
      )}

      <section className="surface p-5">
        <h2 className="text-lg text-ink">Aparelhos</h2>
        {aparelhos.isLoading ? (
          <TxSkeleton n={2} />
        ) : aparelhos.isError ? (
          <div className="mt-3">
            <ErrorBox>{aparelhos.error.message}</ErrorBox>
          </div>
        ) : !aparelhos.data?.length ? (
          <Empty title="Nenhum aparelho" />
        ) : (
          <ul className="mt-3 divide-y divide-line2">
            {aparelhos.data.map((a) => (
              <li key={a.id} className="py-3">
                <div className="flex items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
                    {a.bloqueado ? <Lock size={18} /> : <Smartphone size={18} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">
                      {a.nome ?? "Aparelho"}
                      {a.atual && <span className="ml-2 text-xs text-mut3">este aparelho</span>}
                    </p>
                    <p className={a.bloqueado ? "text-xs text-errt" : "text-xs text-mut3"}>
                      {a.bloqueado
                        ? "Bloqueado"
                        : a.confiavel
                          ? "Confiável"
                          : "Ainda não confirmado"}
                      {a.ultimo_uso && ` · usado em ${fmtData(a.ultimo_uso)}`}
                    </p>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {a.bloqueado ? (
                    <button
                      className="btn btn-ghost gap-2"
                      disabled={enviando}
                      onClick={() => setDesbloquear(a)}
                    >
                      <LockOpen size={16} /> Desbloquear
                    </button>
                  ) : (
                    <button
                      className="btn btn-ghost gap-2"
                      disabled={enviando}
                      onClick={() => setPedido({ tipo: "bloquear", aparelho: a })}
                    >
                      <Lock size={16} /> Bloquear
                    </button>
                  )}
                  <button
                    className="btn btn-ghost gap-2"
                    disabled={enviando}
                    onClick={() => setPedido({ tipo: "remover", aparelho: a })}
                  >
                    <Trash2 size={16} /> Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="surface p-5">
        <h2 className="text-lg text-ink">Sessões abertas</h2>
        {sessoes.isLoading ? (
          <TxSkeleton n={2} />
        ) : sessoes.isError ? (
          <div className="mt-3">
            <ErrorBox>{sessoes.error.message}</ErrorBox>
          </div>
        ) : !sessoes.data?.length ? (
          <Empty title="Nenhuma sessão aberta" />
        ) : (
          <>
            <ul className="mt-3 divide-y divide-line2">
              {sessoes.data.map((s) => (
                <li key={s.sessao_id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">{s.aparelho ?? "Aparelho"}</p>
                    <p className="text-xs text-mut3">
                      {s.atual && "Esta sessão · "}
                      {s.ip ?? "IP desconhecido"}
                      {s.ultimo_uso && ` · ${fmtData(s.ultimo_uso)}`}
                    </p>
                  </div>
                  <button
                    className="btn btn-ghost shrink-0 gap-2"
                    disabled={enviando}
                    onClick={() =>
                      setPedido({ tipo: "encerrar", sessaoId: s.sessao_id, atual: s.atual })
                    }
                  >
                    <LogOut size={16} /> Encerrar
                  </button>
                </li>
              ))}
            </ul>
            {sessoes.data.some((s) => !s.atual) && (
              <button
                className="btn btn-ink mt-3 w-full"
                disabled={enviando}
                onClick={() => setPedido({ tipo: "encerrar-outras" })}
              >
                Encerrar todas as outras
              </button>
            )}
          </>
        )}
      </section>

      <section className="surface p-5">
        <h2 className="flex items-center gap-2 text-lg text-ink">
          <History size={18} /> Atividade recente
        </h2>
        {atividade.isLoading ? (
          <TxSkeleton n={3} />
        ) : atividade.isError ? (
          <div className="mt-3">
            <ErrorBox>{atividade.error.message}</ErrorBox>
          </div>
        ) : !atividade.data?.length ? (
          <Empty title="Nada por aqui ainda" />
        ) : (
          <ul className="mt-3 divide-y divide-line2">
            {atividade.data.map((a) => (
              <li key={a.id} className="py-3">
                <p className="text-sm text-ink">{a.descricao}</p>
                <p className="text-xs text-mut3">
                  {fmtData(a.criado_em)}
                  {a.ip && ` · ${a.ip}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {desbloquear && (
        <LivenessCheck
          onClose={() => setDesbloquear(null)}
          onSuccess={(prova) => {
            const alvo = desbloquear;
            setDesbloquear(null);
            void executar(async () => {
              await desbloquearAparelho(alvo.id, prova);
              return "Aparelho desbloqueado.";
            });
          }}
        />
      )}
    </div>
  );
}

function tituloDoPedido(p: Pedido): string {
  if (p.tipo === "bloquear") return `Bloquear ${p.aparelho.nome ?? "este aparelho"}?`;
  if (p.tipo === "remover") return `Remover ${p.aparelho.nome ?? "este aparelho"}?`;
  if (p.tipo === "encerrar") return p.atual ? "Sair desta sessão?" : "Encerrar esta sessão?";
  return "Encerrar todas as outras sessões?";
}

function detalheDoPedido(p: Pedido): string {
  if (p.tipo === "bloquear")
    return p.aparelho.atual
      ? "É o aparelho que você está usando: você sai da conta agora. Para voltar a usá-lo, entre por outro aparelho e desbloqueie com o rosto."
      : "Ninguém entra mais por ele, e as sessões abertas nele caem na hora. Para desbloquear, você confirma com o rosto.";
  if (p.tipo === "remover")
    return p.aparelho.atual
      ? "É o aparelho que você está usando: você sai da conta agora."
      : "Ele sai da lista. Se alguém entrar por ele de novo, vai precisar da senha e do rosto.";
  if (p.tipo === "encerrar")
    return p.atual
      ? "É a sessão que você está usando: você sai da conta agora."
      : "Quem estiver usando essa sessão volta para a tela de login.";
  return "Todos os outros aparelhos saem da conta. Este continua conectado.";
}
