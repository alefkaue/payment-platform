import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Fingerprint, ScanFace, ShieldCheck } from "lucide-react";
import { aparelhoAtual, confiarAparelho, login, loginBiometria, MODO_API } from "@/lib/api";
import { authPorConta } from "@/lib/empresa";
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

function Login() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState<null | "senha" | "bio">(null);
  // "entrar" = biometria para entrar; "aparelho" = confirmar aparelho novo depois do login.
  const [liveness, setLiveness] = useState<null | "entrar" | "aparelho">(null);
  const [pendente, setPendente] = useState<LoginResposta | null>(null);

  function seguir(r: LoginResposta) {
    entrar(r);
    nav({ to: "/inicio" });
  }

  async function concluir(r: LoginResposta) {
    // Aparelho novo: oferece confirmar com o rosto (senão vale o teto do BC de
    // R$ 200 por Pix e R$ 1.000 por dia neste aparelho).
    if (MODO_API && !(await aparelhoAtual()).confiavel) setPendente(r);
    else seguir(r);
  }

  async function entrarCom(credenciais: { email: string; senha: string }, modo: "senha" | "bio") {
    setErro(null);
    setLoading(modo);
    try {
      await concluir(await login(credenciais));
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  if (pendente)
    return (
      <main className="flex min-h-[100dvh] flex-col bg-page px-5 pb-8 pt-10 md:place-items-center md:justify-center">
        <div className="enter surface mx-auto w-full max-w-md p-6 md:p-9">
          <Wordmark size="lg" />
          <h1 className="mt-6 text-2xl text-ink">Confirme este aparelho</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            É a primeira vez que você entra por aqui. Até confirmar com uma verificação facial, Pix
            e pagamentos ficam limitados a R$ 200 por vez e R$ 1.000 por dia neste aparelho.
          </p>
          {erro && (
            <div className="mt-4">
              <ErrorBox>{erro}</ErrorBox>
            </div>
          )}
          <button className="btn btn-ink mt-6 w-full gap-2" onClick={() => setLiveness("aparelho")}>
            <ScanFace size={20} /> Confirmar com o rosto
          </button>
          <button className="btn btn-ghost mt-3 w-full" onClick={() => seguir(pendente)}>
            Agora não
          </button>
        </div>
        {liveness === "aparelho" && (
          <LivenessCheck
            onClose={() => setLiveness(null)}
            onSuccess={(prova) => {
              setLiveness(null);
              confiarAparelho(prova)
                .then(() => seguir(pendente))
                .catch((err: Error) => setErro(err.message));
            }}
          />
        )}
      </main>
    );

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
                  onClick={() => {
                    setErro(null);
                    if (cert) {
                      if (MODO_API)
                        return setErro(
                          "O acesso com certificado e-CNPJ ainda não está integrado ao banco. Entre com o e-mail ou CPF de quem opera a empresa.",
                        );
                      void entrarCom(
                        { email: email || "voce@email.com", senha: "certificado" },
                        "bio",
                      );
                      return;
                    }
                    if (MODO_API && !email)
                      return setErro("Digite seu e-mail ou CPF para entrar com biometria.");
                    setLiveness("entrar");
                  }}
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

        {!MODO_API && (
          <p className="mt-4 text-center text-xs text-mut3">
            Demonstração: qualquer conta e senha entram. Você acessa a conta pessoal e a da empresa
            pelo seletor no topo.
          </p>
        )}
      </div>

      {liveness === "entrar" && (
        <LivenessCheck
          {...(MODO_API ? { login: email } : {})}
          onClose={() => setLiveness(null)}
          onSuccess={(prova) => {
            setLiveness(null);
            setLoading("bio");
            loginBiometria(email || "voce@email.com", prova)
              .then(concluir)
              .catch((err: Error) => setErro(err.message))
              .finally(() => setLoading(null));
          }}
        />
      )}
    </main>
  );
}
