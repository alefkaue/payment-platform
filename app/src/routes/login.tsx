import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Fingerprint, ShieldCheck } from "lucide-react";
import { login } from "@/lib/api";
import { authPorConta } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Entrar — PayFlow" },
      { name: "description", content: "Entre na sua conta PayFlow." },
      { property: "og:title", content: "Entrar — PayFlow" },
      { property: "og:description", content: "Entre na sua conta PayFlow." },
    ],
  }),
  component: Login,
});

function Login() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState<null | "senha" | "bio">(null);

  async function entrarCom(credenciais: { email: string; senha: string }, modo: "senha" | "bio") {
    setErro(null);
    setLoading(modo);
    try {
      const r = await login(credenciais);
      entrar(r.conta);
      nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="flex min-h-[100dvh] flex-col bg-page px-5 pb-8 pt-10 md:place-items-center md:justify-center">
      <div className="enter mx-auto flex w-full max-w-md flex-1 flex-col md:flex-none">
        <div className="surface flex flex-1 flex-col p-6 md:flex-none md:p-9">
          <Wordmark size="lg" />
          <h1 className="mt-6 text-2xl text-ink">Entre na sua conta</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pessoa física ou empresa — tudo no mesmo lugar.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!email || !senha) return setErro("Informe sua conta e a senha.");
              void entrarCom({ email, senha }, "senha");
            }}
            className="mt-7 space-y-4"
          >
            <Field label="Conta" id="email" hint="E-mail, CPF ou CNPJ.">
              <input
                id="email"
                autoComplete="username"
                className="field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="voce@email.com"
              />
            </Field>
            <Field label="Senha" id="senha">
              <input
                id="senha"
                type="password"
                autoComplete="current-password"
                className="field"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                placeholder="••••••••"
              />
            </Field>
            {erro && <ErrorBox>{erro}</ErrorBox>}
            <button className="btn btn-ink w-full" disabled={loading !== null}>
              {loading === "senha" ? "Entrando…" : "Entrar"}
            </button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-mut3">
            <span className="h-px flex-1 bg-line2" /> ou <span className="h-px flex-1 bg-line2" />
          </div>

          {(() => {
            const auth = authPorConta(email);
            const cert = auth.metodo === "certificado";
            return (
              <>
                <button
                  type="button"
                  disabled={loading !== null}
                  onClick={() =>
                    void entrarCom(
                      { email: email || "voce@email.com", senha: cert ? "certificado" : "biometria" },
                      "bio",
                    )
                  }
                  className="btn btn-ghost w-full gap-2"
                >
                  {cert ? <ShieldCheck size={20} /> : <Fingerprint size={20} />}
                  {loading === "bio"
                    ? "Autenticando…"
                    : cert
                      ? "Entrar com certificado digital"
                      : "Entrar com biometria"}
                </button>
                <p className="mt-2 text-center text-xs text-mut3">
                  {cert
                    ? "Conta empresa: acesso por e-CNPJ (ICP-Brasil) + token. MEI usa biometria."
                    : "Reconhecimento facial do titular."}
                </p>
              </>
            );
          })()}

          <p className="mt-auto pt-7 text-center text-sm text-muted-foreground md:mt-7">
            Novo por aqui?{" "}
            <Link to="/criar-conta" className="font-semibold text-ink underline underline-offset-4">
              Abrir conta
            </Link>
          </p>
        </div>

        <p className="mt-4 text-center text-xs text-mut3">
          Demonstração: qualquer conta e senha entram. Use “empresa” ou “pj” no e-mail para entrar
          como empresa (PJ).
        </p>
      </div>
    </main>
  );
}
