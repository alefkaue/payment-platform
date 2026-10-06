import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { login } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorBox, Field, SplitBar, Wordmark } from "@/components/payflow/ui";

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
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setLoading(true);
    try {
      const r = await login({ email, senha });
      entrar(r.conta);
      nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-page px-4 py-10 md:place-items-center">
      <div className="enter mx-auto w-full max-w-md">
        <div className="surface p-6 md:p-10">
          <Wordmark size="lg" />
          <p className="mt-3 text-muted-foreground">
            Seu banco digital. O imposto se resolve no ato — você recebe o que é seu.
          </p>
          <div className="mt-6 space-y-2">
            <SplitBar liquido={82} imposto={18} />
            <div className="flex justify-between text-xs">
              <span className="text-mut2">Destino recebe</span>
              <span className="text-tax">CBS + IBS → Governo</span>
            </div>
          </div>
          <form onSubmit={submit} className="mt-8 space-y-4">
            <Field label="E-mail" id="email">
              <input
                id="email"
                type="email"
                autoComplete="email"
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
            <button className="btn btn-ink w-full" disabled={loading}>
              {loading ? "Entrando…" : "Entrar"}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Novo por aqui?{" "}
            <Link to="/criar-conta" className="font-semibold text-ink underline underline-offset-4">
              Abrir conta
            </Link>
          </p>
        </div>
        <p className="mt-4 text-center text-xs text-mut2">
          Demonstração: qualquer e-mail e senha entram. Use “empresa” ou “pj” no e-mail para entrar
          como lojista (PJ).
        </p>
      </div>
    </main>
  );
}
