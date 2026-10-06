import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Check, ScanFace, ShieldCheck } from "lucide-react";
import { registrar } from "@/lib/api";
import { PORTES } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { maskDoc } from "@/lib/format";
import type { PortePJ } from "@/lib/types";
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
      { title: "Abrir conta — PayFlow" },
      { name: "description", content: "Abra sua conta PayFlow para pessoa física ou empresa." },
      { property: "og:title", content: "Abrir conta — PayFlow" },
      { property: "og:description", content: "Conta PF ou PJ com split automático de IBS/CBS." },
    ],
  }),
  component: CriarConta,
});

const SETORES = ["Indústria", "Autopeças", "Comércio", "Serviços", "Transporte", "Outro"];

function CriarConta() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const { tipo: tipoInicial } = Route.useSearch();
  const [tipo, setTipo] = useState<"PF" | "PJ">(tipoInicial ?? "PF");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [doc, setDoc] = useState("");
  const [setor, setSetor] = useState(SETORES[0]);
  const [porte, setPorte] = useState<PortePJ>("PME");
  const [facialOk, setFacialOk] = useState(false);
  const [liveness, setLiveness] = useState(false);
  const [certOk, setCertOk] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // MEI e pessoa física usam biometria; demais portes usam certificado digital.
  const usaBiometria = tipo === "PF" || porte === "MEI";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const digits = doc.replace(/\D/g, "");
    if (!nome || !email) return setErro("Preencha nome e e-mail.");
    if (senha.length < 8) return setErro("A senha precisa ter ao menos 8 caracteres.");
    if (digits.length !== (tipo === "PF" ? 11 : 14))
      return setErro(`${tipo === "PF" ? "CPF" : "CNPJ"} incompleto.`);
    if (usaBiometria && !facialOk)
      return setErro("Conclua a verificação facial (prova de vida).");
    if (!usaBiometria && !certOk)
      return setErro("Conecte o certificado digital e-CNPJ da empresa.");
    setLoading(true);
    try {
      const r = await registrar({
        tipo,
        nome,
        email,
        senha,
        documento: digits,
        selfie: null,
      });
      entrar(r.conta);
      nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-page px-4 py-10">
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
                <Field label="Porte da empresa" id="porte" hint="Define como sua conta é verificada.">
                  <select
                    id="porte"
                    className="field"
                    value={porte}
                    onChange={(e) => {
                      setPorte(e.target.value as PortePJ);
                      setFacialOk(false);
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
              </>
            )}

            {usaBiometria ? (
              <FacialStep ok={facialOk} onStart={() => setLiveness(true)} />
            ) : (
              <CertificadoDigital
                ok={certOk}
                onConnect={() => setCertOk(true)}
                dupla={PORTES[porte].duplaAssinatura}
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
          onClose={() => setLiveness(false)}
          onSuccess={() => {
            setLiveness(false);
            setFacialOk(true);
          }}
        />
      )}
    </main>
  );
}

/** Passo de verificação facial com prova de vida (PF e MEI). */
function FacialStep({ ok, onStart }: { ok: boolean; onStart: () => void }) {
  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-11 w-11 shrink-0 place-items-center rounded-full",
            ok ? "bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos" : "bg-tint text-ink",
          )}
        >
          {ok ? <Check size={22} strokeWidth={3} /> : <ScanFace size={22} />}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">
            {ok ? "Verificação facial concluída" : "Verificação facial (prova de vida)"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Pela câmera, ao vivo — você vai piscar e virar o rosto. Sem foto, nada é armazenado.
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
}: {
  ok: boolean;
  onConnect: () => void;
  dupla: boolean;
}) {
  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-11 w-11 shrink-0 place-items-center rounded-full",
            ok ? "bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos" : "bg-tint text-ink",
          )}
        >
          {ok ? <Check size={22} strokeWidth={3} /> : <ShieldCheck size={22} />}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-ink">
            {ok ? "Certificado e-CNPJ conectado" : "Certificado digital e-CNPJ"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Autenticação por ICP-Brasil (A1 em arquivo ou A3 em token) — o mesmo que assina suas
            notas fiscais. Sem selfie.
          </p>
          {!ok && (
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
