import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  BadgeCheck,
  Clock,
  CircleX,
  ChevronRight,
  LogOut,
  Settings,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { aparelhoAtual, minhaConta, minhaVerificacao, reenviarDocumento } from "@/lib/api";
import type { DocumentoIdentidade, TipoDocumentoPessoa } from "@/lib/types";
import { DocumentoPessoa } from "@/components/payflow/documento-pessoa";
import { PAPEIS, PORTES, REGIMES_APURACAO } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { fmtBRL, iniciais } from "@/lib/format";
import { ErrorBox, PageTitle } from "@/components/payflow/ui";

export const Route = createFileRoute("/_app/perfil")({
  head: () => ({ meta: [{ title: "Meu perfil — Astro" }] }),
  component: Perfil,
});

function Perfil() {
  const { conta: sessao, pessoa, sair } = useAuth();
  const nav = useNavigate();
  const conta = useQuery({ queryKey: ["conta", sessao?.numero], queryFn: minhaConta });
  const aparelho = useQuery({ queryKey: ["aparelho"], queryFn: aparelhoAtual });
  const ehPJ = sessao?.tipo === "PJ";
  const c = conta.data;
  const confiavel = aparelho.data?.confiavel ?? true;
  const cache = useQueryClient();
  const verificacao = useQuery({ queryKey: ["identidade"], queryFn: minhaVerificacao });
  const [enviando, setEnviando] = useState(false);
  const [tipoDoc, setTipoDoc] = useState<TipoDocumentoPessoa>("cnh");
  const [frente, setFrente] = useState<string | null>(null);
  const [verso, setVerso] = useState<string | null>(null);
  const envio = useMutation({
    mutationFn: reenviarDocumento,
    onSuccess: async (resultado) => {
      // O reenvio pode ser recusado sem mudar o status da pessoa no servidor.
      const atual = await minhaVerificacao();
      cache.setQueryData(["identidade"], {
        ...atual,
        caso: { id: resultado.caso_id, status: resultado.status, motivos: resultado.motivos },
      });
      setEnviando(false);
      setFrente(null);
      setVerso(null);
    },
  });
  const status = verificacao.data?.status;
  const verificada = status === "aprovado";
  const recusada = status === "reprovado";
  const rotulo = verificada
    ? "Verificada"
    : recusada
      ? "Recusada"
      : status === "em_analise"
        ? "Em análise"
        : "Pendente";
  const cor = verificada ? "text-pos" : recusada ? "text-errt" : "text-pending";
  const Icone = verificada ? BadgeCheck : recusada ? CircleX : Clock;

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Seus dados, verificação e dispositivos.">Meu perfil</PageTitle>

      {/* Cabeçalho do perfil */}
      <section className="surface flex items-center gap-4 p-6">
        <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-ink text-xl font-semibold text-ink-foreground">
          {iniciais(c?.nome)}
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold text-ink">{c?.nome ?? "…"}</h2>
          <p className="truncate text-sm text-mut2">
            {ehPJ ? "Conta empresa (PJ)" : "Conta pessoa física"}
          </p>
          <span
            className={`mt-1 inline-flex items-center gap-1 rounded-full bg-tint px-2.5 py-0.5 text-xs font-medium ${cor}`}
          >
            <Icone size={13} />{" "}
            {verificacao.isPending
              ? "Carregando verificação…"
              : verificacao.isError
                ? "Verificação indisponível"
                : rotulo}
          </span>
        </div>
      </section>

      {/* Dados */}
      <section className="surface overflow-hidden">
        <h2 className="px-5 pt-5 text-lg text-ink">Dados cadastrais</h2>
        <ul className="mt-2 divide-y divide-border px-5 pb-2 text-sm">
          <Dado label={ehPJ ? "Razão social" : "Nome completo"} valor={c?.nome ?? "—"} />
          {ehPJ ? (
            <>
              <Dado label="CNPJ" valor={c?.cnpj ?? "—"} />
              <Dado label="Setor" valor={c?.setor ?? "—"} />
              <Dado label="Porte" valor={c?.porte ? PORTES[c.porte].label : "—"} />
              {c?.regime_apuracao && (
                <Dado label="Apuração" valor={REGIMES_APURACAO[c.regime_apuracao].label} />
              )}
              <Dado label="Seu papel" valor={PAPEIS[sessao?.papel ?? "consulta"]} />
              <Dado
                label="Sua alçada"
                valor={sessao?.alcada == null ? "Sem limite" : fmtBRL(sessao.alcada)}
              />
            </>
          ) : (
            <>
              <Dado label="CPF" valor={mascararCpf(pessoa?.cpf)} />
              <Dado label="E-mail" valor={pessoa?.email ?? "—"} />
            </>
          )}
          <Dado label="Agência / conta" valor={`${c?.agencia ?? "0001"} / ${c?.numero ?? "—"}`} />
        </ul>
      </section>

      <section className="surface space-y-4 p-5">
        <h2 className="text-lg text-ink">Verificação de identidade</h2>
        {verificacao.isPending ? (
          <p className="text-sm text-mut3">Carregando verificação…</p>
        ) : verificacao.isError ? (
          <>
            <ErrorBox>{verificacao.error.message}</ErrorBox>
            <button className="btn btn-ghost" onClick={() => void verificacao.refetch()}>
              Tentar novamente
            </button>
          </>
        ) : (
          <>
            <p className={`flex items-center gap-2 font-medium ${cor}`}>
              <Icone size={20} />
              {rotulo}
            </p>
            {!!verificacao.data?.caso?.motivos.length && (
              <ul className="space-y-2 text-sm text-mut3">
                {verificacao.data.caso.motivos.map((motivo, i) => (
                  <li key={i}>{motivoSimples(motivo)}</li>
                ))}
              </ul>
            )}
            {!verificada && !enviando && (
              <button
                className="btn btn-ink w-full"
                onClick={() => {
                  envio.reset();
                  setEnviando(true);
                }}
              >
                Enviar documento
              </button>
            )}
            {!verificada && enviando && (
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!frente || (tipoDoc !== "passaporte" && !verso)) return;
                  const documento: DocumentoIdentidade = {
                    tipo: tipoDoc,
                    frente,
                    ...(tipoDoc !== "passaporte" && verso ? { verso } : {}),
                  };
                  envio.mutate(documento);
                }}
              >
                <p className="text-sm text-mut3">
                  Foto nítida, sem reflexo, com o documento inteiro. As imagens não ficam guardadas.
                </p>
                <fieldset disabled={envio.isPending} className="space-y-4">
                  <DocumentoPessoa
                    tipo={tipoDoc}
                    frente={frente}
                    verso={verso}
                    onTipo={setTipoDoc}
                    onFrente={setFrente}
                    onVerso={setVerso}
                  />
                </fieldset>
                {envio.error && <ErrorBox>{envio.error.message}</ErrorBox>}
                <button
                  className="btn btn-ink w-full"
                  disabled={envio.isPending || !frente || (tipoDoc !== "passaporte" && !verso)}
                >
                  {envio.isPending ? "Enviando…" : "Enviar para verificação"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost w-full"
                  disabled={envio.isPending}
                  onClick={() => {
                    setEnviando(false);
                    setFrente(null);
                    setVerso(null);
                  }}
                >
                  Cancelar
                </button>
              </form>
            )}
          </>
        )}
      </section>

      {/* Segurança do aparelho */}
      <section className="surface p-5">
        <h2 className="text-lg text-ink">Este aparelho</h2>
        <div className="mt-3 flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
            {confiavel ? <ShieldCheck size={20} /> : <Smartphone size={20} />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-ink">
              {confiavel ? "Aparelho confiável" : "Aparelho não confirmado"}
            </p>
            <p className="text-xs text-mut3">
              {confiavel
                ? "Verificação facial pedida em pagamentos acima de R$ 500."
                : "Confirme com o rosto para liberar limites maiores."}
            </p>
          </div>
          <Link to="/config" className="text-mut3 hover:text-ink" aria-label="Gerenciar segurança">
            <ChevronRight size={20} />
          </Link>
        </div>
      </section>

      {/* Atalhos */}
      <section className="surface overflow-hidden">
        <LinhaLink to="/config" icon={<Settings size={18} />} label="Configurações da conta" />
      </section>

      <button
        onClick={() => {
          sair();
          nav({ to: "/login" });
        }}
        className="btn btn-ghost w-full gap-2 text-err"
      >
        <LogOut size={18} /> Sair da conta
      </button>
    </div>
  );
}

function motivoSimples(motivo: string): string {
  if (/sem OCR/i.test(motivo)) return "Precisamos analisar os dados do documento com mais cuidado.";
  if (/MRZ.*nascimento|nascimento.*MRZ/i.test(motivo))
    return "A data de nascimento do documento não confere com o cadastro.";
  if (/MRZ|leitura mecânica/i.test(motivo))
    return "Não conseguimos confirmar os códigos de segurança do documento.";
  if (/faixa de dúvida/i.test(motivo))
    return "Precisamos conferir se a foto do documento corresponde ao seu rosto.";
  if (/sem selfie/i.test(motivo))
    return "Não temos sua foto de verificação para comparar com o documento.";
  return motivo;
}

/** CPF mascarado como no Pix: •••.456.789-•• */
function mascararCpf(cpf?: string): string {
  const d = (cpf ?? "").replace(/\D/g, "");
  return d.length === 11 ? `•••.${d.slice(3, 6)}.${d.slice(6, 9)}-••` : "—";
}

function Dado({ label, valor }: { label: string; valor: string }) {
  return (
    <li className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-mut3">{label}</span>
      <span className="truncate font-medium text-ink">{valor}</span>
    </li>
  );
}

function LinhaLink({ to, icon, label }: { to: "/config"; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 px-5 py-4 transition hover:bg-tint">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-tint text-ink">{icon}</span>
      <span className="flex-1 font-medium text-ink">{label}</span>
      <ChevronRight size={18} className="text-mut3" />
    </Link>
  );
}
