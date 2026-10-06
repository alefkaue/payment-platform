import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ScanFace } from "lucide-react";
import { aparelhoAtual, confiarAparelho, login, MODO_API } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { LoginResposta } from "@/lib/types";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

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

/**
 * Login da PESSOA (e-mail + senha). Quem tem empresa troca para a conta PJ pelo
 * seletor no cabeçalho — como nos bancos digitais. Se este aparelho ainda não é
 * confiável, oferecemos confirmar com verificação facial (senão valem os limites
 * de aparelho novo do Banco Central: R$ 200 por Pix e R$ 1.000 por dia).
 */
function Login() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendente, setPendente] = useState<LoginResposta | null>(null);
  const [liveness, setLiveness] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !senha) return setErro("Informe e-mail e senha.");
    setErro(null);
    setLoading(true);
    try {
      const r = await login({ email, senha });
      if (MODO_API && !(await aparelhoAtual()).confiavel) {
        setPendente(r);
        return;
      }
      entrar(r);
      nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function seguir(r: LoginResposta) {
    entrar(r);
    nav({ to: "/inicio" });
  }

  return (
    <main className="flex min-h-[100dvh] flex-col bg-page px-5 pb-8 pt-10 md:place-items-center md:justify-center">
      <div className="enter mx-auto flex w-full max-w-md flex-1 flex-col md:flex-none">
        <div className="surface flex flex-1 flex-col p-6 md:flex-none md:p-9">
          <Wordmark size="lg" />
          {pendente ? (
            <>
              <h1 className="mt-6 text-2xl text-ink">Confirme este aparelho</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                É a primeira vez que você entra por aqui. Até confirmar com uma verificação facial,
                Pix e pagamentos ficam limitados a R$ 200 por vez e R$ 1.000 por dia neste aparelho.
              </p>
              {erro && (
                <div className="mt-4">
                  <ErrorBox>{erro}</ErrorBox>
                </div>
              )}
              <button className="btn btn-ink mt-6 w-full gap-2" onClick={() => setLiveness(true)}>
                <ScanFace size={20} /> Confirmar com o rosto
              </button>
              <button className="btn btn-ghost mt-3 w-full" onClick={() => seguir(pendente)}>
                Agora não
              </button>
            </>
          ) : (
            <>
              <h1 className="mt-6 text-2xl text-ink">Entre na sua conta</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Com o seu login você acessa a conta pessoal e as das suas empresas.
              </p>
              <form onSubmit={submit} className="mt-7 space-y-4">
                <Field label="E-mail" id="email">
                  <input
                    id="email"
                    type="email"
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
                <button className="btn btn-ink w-full" disabled={loading}>
                  {loading ? "Entrando…" : "Entrar"}
                </button>
              </form>
              <p className="mt-auto pt-7 text-center text-sm text-muted-foreground md:mt-7">
                Novo por aqui?{" "}
                <Link
                  to="/criar-conta"
                  className="font-semibold text-ink underline underline-offset-4"
                >
                  Abrir conta
                </Link>
              </p>
            </>
          )}
        </div>

        {!MODO_API && (
          <p className="mt-4 text-center text-xs text-mut3">
            Demonstração: qualquer e-mail e senha entram. Você acessa a conta pessoal e a da empresa
            pelo seletor no topo.
          </p>
        )}
      </div>

      {liveness && pendente && (
        <LivenessCheck
          onClose={() => setLiveness(false)}
          onSuccess={(prova) => {
            setLiveness(false);
            confiarAparelho(prova)
              .then(() => seguir(pendente))
              .catch((err: Error) => setErro(err.message));
          }}
        />
      )}
    </main>
  );
}
