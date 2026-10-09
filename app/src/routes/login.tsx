import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ScanFace } from "lucide-react";
import { concluirLogin, login, MODO_API, novoDesafioLogin } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { LoginEtapaMfa } from "@/lib/types";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Entrar — Astro" },
      { name: "description", content: "Entre na sua conta Astro." },
      { property: "og:title", content: "Entrar — Astro" },
      { property: "og:description", content: "Entre na sua conta Astro." },
    ],
  }),
  component: Login,
});

/**
 * Login em dois fatores, sempre: a senha (algo que você sabe) e o rosto com prova
 * de vida (algo que você é). Na conta empresa é igual: cada pessoa entra com o
 * próprio login; o papel e a alçada definem o que ela pode fazer.
 */
function Login() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Senha conferida: falta o rosto.
  const [etapa, setEtapa] = useState<LoginEtapaMfa | null>(null);
  const [camera, setCamera] = useState(false);

  async function enviarSenha(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !senha) return setErro("Informe sua conta e a senha.");
    setErro(null);
    setLoading(true);
    try {
      setEtapa(await login({ email, senha }));
      setCamera(true);
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function tentarDeNovo() {
    if (!etapa) return;
    setErro(null);
    setLoading(true);
    try {
      setEtapa(await novoDesafioLogin(etapa));
      setCamera(true);
    } catch (err) {
      // mfa_token vencido (5 min) ou tentativas demais: volta para a senha.
      setEtapa(null);
      setSenha("");
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] justify-center bg-black">
      <main className="flex min-h-[100dvh] w-full max-w-[460px] flex-col bg-page px-5 pb-8 pt-10 shadow-2xl">
        <div className="enter mx-auto flex w-full max-w-md flex-1 flex-col md:flex-none">
          <div className="surface flex flex-1 flex-col p-6 md:flex-none md:p-9">
            <Wordmark size="lg" />
            {etapa ? (
              <>
                <h1 className="mt-6 text-2xl text-ink">Agora, o seu rosto</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Senha conferida. Para entrar, confirme que é você: olhe para a câmera e pisque
                  devagar 3 vezes.
                </p>
                {erro && (
                  <div className="mt-4">
                    <ErrorBox>{erro}</ErrorBox>
                  </div>
                )}
                <button
                  className="btn btn-ink mt-6 w-full gap-2"
                  disabled={loading}
                  onClick={() => (erro ? void tentarDeNovo() : setCamera(true))}
                >
                  <ScanFace size={20} /> {loading ? "Entrando…" : "Verificar meu rosto"}
                </button>
                <button
                  className="btn btn-ghost mt-3 w-full"
                  disabled={loading}
                  onClick={() => {
                    setEtapa(null);
                    setErro(null);
                    setSenha("");
                  }}
                >
                  Voltar
                </button>
              </>
            ) : (
              <>
                <h1 className="mt-6 text-2xl text-ink">Entre na sua conta</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Pessoa física ou empresa — tudo no mesmo lugar.
                </p>

                <form onSubmit={enviarSenha} className="mt-7 space-y-4">
                  <Field
                    label="Conta"
                    id="email"
                    hint="E-mail ou CPF. Contas de empresa entram pelo login de quem as opera."
                  >
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
                      placeholder="••••••••••"
                    />
                  </Field>
                  {erro && <ErrorBox>{erro}</ErrorBox>}
                  <button className="btn btn-ink w-full" disabled={loading}>
                    {loading ? "Conferindo…" : "Continuar"}
                  </button>
                </form>
                <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-xs text-mut3">
                  <ScanFace size={14} /> Depois da senha, confirmamos o seu rosto.
                </p>
              </>
            )}

            <p className="mt-auto pt-7 text-center text-sm text-muted-foreground md:mt-7">
              Novo por aqui?{" "}
              <Link
                to="/criar-conta"
                className="font-semibold text-ink underline underline-offset-4"
              >
                Abrir conta
              </Link>
            </p>
          </div>

          {!MODO_API && !etapa && (
            <p className="mt-4 text-center text-xs text-mut3">
              Demonstração: quem criou conta aqui entra com o próprio e-mail e senha; outro e-mail
              entra na conta de exemplo (pessoal e empresa, troca pelo seletor no topo).
            </p>
          )}
        </div>

        {etapa && camera && (
          <LivenessCheck
            desafio={etapa.desafio}
            onClose={() => setCamera(false)}
            onSuccess={(prova) => {
              setCamera(false);
              setLoading(true);
              concluirLogin(etapa, prova)
                .then((r) => {
                  entrar(r);
                  nav({ to: "/inicio" });
                })
                .catch((err: Error) => setErro(err.message))
                .finally(() => setLoading(false));
            }}
          />
        )}
      </main>
    </div>
  );
}
