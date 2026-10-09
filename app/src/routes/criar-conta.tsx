import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Check, ScanFace, ShieldCheck } from "lucide-react";
import { MODO_API, registrar } from "@/lib/api";
import { PORTES, REGIMES_APURACAO } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { maskDoc } from "@/lib/format";
import type { PortePJ, ProvaBiometrica, RegimeApuracao } from "@/lib/types";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";
import { cn } from "@/lib/utils";

type Busca = { tipo?: "PF" | "PJ" };

export const Route = createFileRoute("/criar-conta")({
  validateSearch: (s: Record<string, unknown>): Busca => {
    const t = s["tipo"];
    return t === "PJ" || t === "PF" ? { tipo: t } : {};
  },
  head: () => ({
    meta: [
      { title: "Abrir conta — Astro" },
      { name: "description", content: "Abra sua conta Astro para pessoa física ou empresa." },
      { property: "og:title", content: "Abrir conta — Astro" },
      { property: "og:description", content: "Conta PF ou PJ com split automático de IBS/CBS." },
    ],
  }),
  component: CriarConta,
});

const SETORES = ["Indústria", "Autopeças", "Comércio", "Serviços", "Transporte", "Outro"];
// O desafio de biometria vale 2 minutos no servidor; refazemos se passar disso.
const VALIDADE_PROVA_MS = 100_000;

function CriarConta() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const { tipo: tipoInicial } = Route.useSearch();
  const [tipo, setTipo] = useState<"PF" | "PJ">(tipoInicial ?? "PF");
  const [nome, setNome] = useState("");
  const [representante, setRepresentante] = useState("");
  const [cpf, setCpf] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [doc, setDoc] = useState("");
  const [setor, setSetor] = useState(SETORES[0] ?? "Indústria");
  const [porte, setPorte] = useState<PortePJ>("PME");
  const [regime, setRegime] = useState<RegimeApuracao>("regular");
  const [prova, setProva] = useState<{ p: ProvaBiometrica; em: number } | null>(null);
  const [liveness, setLiveness] = useState(false);
  const [certOk, setCertOk] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // MEI e pessoa física usam biometria; demais portes usam certificado digital.
  // No banco de verdade, quem opera a empresa é uma pessoa: a biometria do
  // representante é sempre exigida; o certificado fica para assinar lotes.
  const usaBiometria = tipo === "PF" || porte === "MEI" || MODO_API;
  const usaCertificado = tipo === "PJ" && porte !== "MEI";
  const facialOk = prova !== null && Date.now() - prova.em < VALIDADE_PROVA_MS;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const digits = doc.replace(/\D/g, "");
    if (!nome || !email) return setErro("Preencha nome e e-mail.");
    if (senha.length < 8) return setErro("A senha precisa ter ao menos 8 caracteres.");
    if (digits.length !== (tipo === "PF" ? 11 : 14))
      return setErro(`${tipo === "PF" ? "CPF" : "CNPJ"} incompleto.`);
    if (tipo === "PJ" && (!representante || cpf.replace(/\D/g, "").length !== 11))
      return setErro("Informe o nome e o CPF de quem vai operar a conta da empresa.");
    if (usaBiometria && !facialOk)
      return setErro(
        prova
          ? "A verificação facial expirou. Faça de novo."
          : "Conclua a verificação facial (prova de vida).",
      );
    if (usaCertificado && !MODO_API && !certOk)
      return setErro("Conecte o certificado digital e-CNPJ da empresa.");
    setLoading(true);
    try {
      const pessoaCpf = tipo === "PF" ? digits : cpf.replace(/\D/g, "");
      const r = await registrar({
        nome: tipo === "PF" ? nome : representante,
        email,
        senha,
        cpf: pessoaCpf,
        biometria: prova?.p ?? { desafio_id: "demo", quadros: [] },
        ...(tipo === "PJ"
          ? {
              empresa: {
                cnpj: digits,
                nome_fantasia: nome,
                porte,
                regime_apuracao: porte === "MEI" ? "mei" : regime,
                setor,
              },
            }
          : {}),
      });
      entrar(tipo === "PJ" ? { ...r, conta: r.contas.find((c) => c.tipo === "PJ") ?? r.conta } : r);
      nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
      setProva(null); // o desafio foi consumido: uma nova tentativa precisa de outra verificação
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] justify-center bg-black">
      <main className="min-h-[100dvh] w-full max-w-[460px] bg-page px-4 py-10 shadow-2xl">
        <div className="enter mx-auto w-full max-w-lg">
          <div className="surface p-6 md:p-10">
            <Wordmark />
            <h1 className="mt-6 text-3xl text-ink">Abrir conta</h1>
            <form onSubmit={submit} className="mt-6 space-y-4">
              <div
                role="radiogroup"
                aria-label="Tipo de conta"
                className="grid grid-cols-2 rounded-full bg-tint p-1"
              >
                {(["PF", "PJ"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={tipo === t}
                    onClick={() => {
                      setTipo(t);
                      setDoc("");
                    }}
                    className={cn(
                      "h-10 rounded-full text-sm font-semibold transition-colors duration-200",
                      tipo === t
                        ? "bg-ink text-ink-foreground shadow-soft"
                        : "text-mut2 hover:text-ink",
                    )}
                  >
                    {t === "PF" ? "Pessoa física" : "Empresa (PJ)"}
                  </button>
                ))}
              </div>
              <Field label={tipo === "PF" ? "Nome" : "Razão social"} id="nome">
                <input
                  id="nome"
                  className="field"
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                />
              </Field>
              <Field label="E-mail" id="email">
                <input
                  id="email"
                  type="email"
                  className="field"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field label="Senha" id="senha" hint="Mínimo de 8 caracteres.">
                <input
                  id="senha"
                  type="password"
                  className="field"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                />
              </Field>
              <Field label={tipo === "PF" ? "CPF" : "CNPJ"} id="doc">
                <input
                  id="doc"
                  inputMode="numeric"
                  className="field tabular"
                  value={doc}
                  onChange={(e) => setDoc(maskDoc(e.target.value, tipo))}
                  placeholder={tipo === "PF" ? "000.000.000-00" : "00.000.000/0000-00"}
                />
              </Field>
              {tipo === "PJ" && (
                <>
                  <Field label="Setor de atuação" id="setor">
                    <select
                      id="setor"
                      className="field"
                      value={setor}
                      onChange={(e) => setSetor(e.target.value)}
                    >
                      {SETORES.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Porte da empresa"
                    id="porte"
                    hint="Define como sua conta é verificada."
                  >
                    <select
                      id="porte"
                      className="field"
                      value={porte}
                      onChange={(e) => {
                        setPorte(e.target.value as PortePJ);
                        setCertOk(false);
                      }}
                    >
                      {(Object.keys(PORTES) as PortePJ[]).map((p) => (
                        <option key={p} value={p}>
                          {PORTES[p].label} — {PORTES[p].faturamento}
                        </option>
                      ))}
                    </select>
                  </Field>
                  {porte !== "MEI" && (
                    <Field
                      label="Regime de apuração"
                      id="regime"
                      hint={REGIMES_APURACAO[regime].dica}
                    >
                      <select
                        id="regime"
                        className="field"
                        value={regime}
                        onChange={(e) => setRegime(e.target.value as RegimeApuracao)}
                      >
                        {(["regular", "simples"] as const).map((r) => (
                          <option key={r} value={r}>
                            {REGIMES_APURACAO[r].label}
                          </option>
                        ))}
                      </select>
                    </Field>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Representante (sócio)" id="rep">
                      <input
                        id="rep"
                        className="field"
                        value={representante}
                        onChange={(e) => setRepresentante(e.target.value)}
                      />
                    </Field>
                    <Field label="CPF do representante" id="cpf">
                      <input
                        id="cpf"
                        inputMode="numeric"
                        className="field tabular"
                        value={cpf}
                        onChange={(e) => setCpf(maskDoc(e.target.value, "PF"))}
                        placeholder="000.000.000-00"
                      />
                    </Field>
                  </div>
                </>
              )}

              {usaBiometria && <FacialStep ok={facialOk} onStart={() => setLiveness(true)} />}
              {usaCertificado && (
                <CertificadoDigital
                  ok={certOk}
                  onConnect={() => setCertOk(true)}
                  dupla={PORTES[porte].duplaAssinatura}
                  opcional={MODO_API}
                />
              )}
              {erro && <ErrorBox>{erro}</ErrorBox>}
              <button className="btn btn-ink w-full" disabled={loading}>
                {loading ? "Criando…" : "Criar conta"}
              </button>
            </form>
            <p className="mt-6 text-center text-sm text-muted-foreground">
              Já tem conta?{" "}
              <Link to="/login" className="font-semibold text-ink underline underline-offset-4">
                Entrar
              </Link>
            </p>
          </div>
        </div>

        {liveness && (
          <LivenessCheck
            modo="cadastro"
            onClose={() => setLiveness(false)}
            onSuccess={(p) => {
              setLiveness(false);
              setProva({ p, em: Date.now() });
            }}
          />
        )}
      </main>
    </div>
  );
}

/** Passo de verificação facial com prova de vida. */
function FacialStep({ ok, onStart }: { ok: boolean; onStart: () => void }) {
  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-11 w-11 shrink-0 place-items-center rounded-full",
            ok
              ? "bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos"
              : "bg-tint text-ink",
          )}
        >
          {ok ? <Check size={22} strokeWidth={3} /> : <ScanFace size={22} />}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">
            {ok ? "Verificação facial concluída" : "Verificação facial (prova de vida)"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Pela câmera, ao vivo — olhe de frente e vire o rosto para o lado pedido. Guardamos só um
            código do rosto, criptografado.
          </p>
          {!ok && (
            <button
              type="button"
              onClick={onStart}
              className="mt-2 text-sm font-semibold text-ink underline underline-offset-4"
            >
              Iniciar verificação
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Verificação por certificado digital e-CNPJ (PME e grandes empresas). */
function CertificadoDigital({
  ok,
  onConnect,
  dupla,
  opcional,
}: {
  ok: boolean;
  onConnect: () => void;
  dupla: boolean;
  opcional: boolean;
}) {
  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-11 w-11 shrink-0 place-items-center rounded-full",
            ok
              ? "bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos"
              : "bg-tint text-ink",
          )}
        >
          {ok ? <Check size={22} strokeWidth={3} /> : <ShieldCheck size={22} />}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">
            {ok ? "Certificado e-CNPJ conectado" : "Certificado digital e-CNPJ"}
            {opcional && !ok && <span className="font-normal text-mut3"> · conectar depois</span>}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Autenticação por ICP-Brasil (A1 em arquivo ou A3 em token) — o mesmo que assina suas
            notas fiscais.
            {opcional &&
              " A integração com o certificado está em andamento; você pode vincular depois."}
          </p>
          {!ok && !opcional && (
            <button
              type="button"
              onClick={onConnect}
              className="mt-2 text-sm font-semibold text-ink underline underline-offset-4"
            >
              Conectar certificado ou token
            </button>
          )}
          {dupla && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-tax-bg px-2.5 py-1 text-[11px] font-medium text-tax2">
              <ShieldCheck size={12} /> Dupla autorização e alçadas por assinante
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
