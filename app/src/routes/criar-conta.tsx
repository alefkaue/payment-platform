import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Building2, ScanFace } from "lucide-react";
import { registrar } from "@/lib/api";
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
      { title: "Abrir conta — PayFlow" },
      { name: "description", content: "Abra sua conta PayFlow para pessoa física ou empresa." },
      { property: "og:title", content: "Abrir conta — PayFlow" },
      { property: "og:description", content: "Conta PF ou PJ com split de IBS/CBS nas cobranças." },
    ],
  }),
  component: CriarConta,
});

/**
 * Cadastro. Toda conta começa por uma PESSOA (CPF + verificação facial). Para
 * empresa, a mesma pessoa informa o CNPJ: o banco confere na Receita e, quando o
 * quadro de sócios está disponível, exige que ela seja sócia. Ela vira admin da
 * empresa e pode adicionar outras pessoas com papéis e alçadas depois.
 */
function CriarConta() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const { tipo: tipoInicial } = Route.useSearch();
  const [tipo, setTipo] = useState<"PF" | "PJ">(tipoInicial ?? "PF");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [cpf, setCpf] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [fantasia, setFantasia] = useState("");
  const [porte, setPorte] = useState<PortePJ>("PME");
  const [regime, setRegime] = useState<RegimeApuracao>("regular");
  const [liveness, setLiveness] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function validar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!nome || !email) return setErro("Preencha nome e e-mail.");
    if (senha.length < 8) return setErro("A senha precisa ter ao menos 8 caracteres.");
    if (cpf.replace(/\D/g, "").length !== 11) return setErro("CPF incompleto.");
    if (tipo === "PJ" && cnpj.replace(/\D/g, "").length !== 14) return setErro("CNPJ incompleto.");
    setLiveness(true);
  }

  async function criar(prova: ProvaBiometrica) {
    setLoading(true);
    try {
      const r = await registrar({
        nome,
        email,
        senha,
        cpf: cpf.replace(/\D/g, ""),
        biometria: prova,
        ...(tipo === "PJ"
          ? {
              empresa: {
                cnpj: cnpj.replace(/\D/g, ""),
                ...(fantasia ? { nome_fantasia: fantasia } : {}),
                porte,
                regime_apuracao: porte === "MEI" ? "mei" : regime,
              },
            }
          : {}),
      });
      entrar(r);
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
          <form onSubmit={validar} className="mt-6 space-y-4">
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
                  onClick={() => setTipo(t)}
                  className={cn(
                    "h-10 rounded-full text-sm font-semibold transition-colors duration-200",
                    tipo === t
                      ? "bg-ink text-ink-foreground shadow-soft"
                      : "text-mut2 hover:text-ink",
                  )}
                >
                  {t === "PF" ? "Pessoa física" : "Pessoa + empresa"}
                </button>
              ))}
            </div>

            <Field label="Seu nome" id="nome">
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
            <Field label="Seu CPF" id="cpf">
              <input
                id="cpf"
                inputMode="numeric"
                className="field tabular"
                value={cpf}
                onChange={(e) => setCpf(maskDoc(e.target.value, "PF"))}
                placeholder="000.000.000-00"
              />
            </Field>

            {tipo === "PJ" && (
              <div className="space-y-4 rounded-[18px] border border-line2 p-4">
                <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <Building2 size={16} /> Dados da empresa
                </p>
                <Field
                  label="CNPJ"
                  id="cnpj"
                  hint="Conferimos na Receita. Você precisa ser sócio(a)."
                >
                  <input
                    id="cnpj"
                    inputMode="numeric"
                    className="field tabular"
                    value={cnpj}
                    onChange={(e) => setCnpj(maskDoc(e.target.value, "PJ"))}
                    placeholder="00.000.000/0000-00"
                  />
                </Field>
                <Field label="Nome fantasia (opcional)" id="fantasia">
                  <input
                    id="fantasia"
                    className="field"
                    value={fantasia}
                    onChange={(e) => setFantasia(e.target.value)}
                  />
                </Field>
                <Field label="Porte" id="porte">
                  <select
                    id="porte"
                    className="field"
                    value={porte}
                    onChange={(e) => setPorte(e.target.value as PortePJ)}
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
              </div>
            )}

            <p className="flex items-start gap-2 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
              <ScanFace size={18} className="mt-0.5 shrink-0" />
              Ao continuar, fazemos uma verificação facial rápida pela câmera: olhar de frente e
              virar o rosto para o lado que o app pedir.
            </p>
            {erro && <ErrorBox>{erro}</ErrorBox>}
            <button className="btn btn-ink w-full" disabled={loading}>
              {loading ? "Criando…" : "Continuar"}
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
          onSuccess={(prova) => {
            setLiveness(false);
            void criar(prova);
          }}
        />
      )}
    </main>
  );
}
