import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CheckCircle2, ScanFace } from "lucide-react";
import { concluirRecuperacao, iniciarRecuperacao } from "@/lib/api";
import type { EtapaRecuperacao } from "@/lib/types";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";

export const Route = createFileRoute("/recuperar-senha")({
  head: () => ({
    meta: [
      { title: "Recuperar senha — Astro" },
      { name: "description", content: "Crie uma senha nova confirmando que é você." },
    ],
  }),
  component: RecuperarSenha,
});

/**
 * Esqueci a senha. Sem link por e-mail ou SMS: quem prova que é você é o rosto,
 * conferido com o do cadastro (SECURITY_AUDIT A-16).
 * 1) e-mail/CPF + data de nascimento + senha nova; 2) prova de vida completa.
 */
function RecuperarSenha() {
  const [login, setLogin] = useState("");
  const [nascimento, setNascimento] = useState("");
  const [senha, setSenha] = useState("");
  const [repetida, setRepetida] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [etapa, setEtapa] = useState<EtapaRecuperacao | null>(null);
  const [camera, setCamera] = useState(false);
  const [feito, setFeito] = useState(false);

  async function continuar(e: React.FormEvent) {
    e.preventDefault();
    if (!login || !nascimento || !senha) return setErro("Preencha todos os campos.");
    if (senha.length < 10) return setErro("A senha nova precisa ter ao menos 10 caracteres.");
    if (senha !== repetida) return setErro("As duas senhas não são iguais.");
    setErro(null);
    setLoading(true);
    try {
      setEtapa(await iniciarRecuperacao(login, nascimento));
      setCamera(true);
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function recomecar(msg: string | null) {
    setEtapa(null);
    setCamera(false);
    setErro(msg);
  }

  return (
    <div className="flex min-h-[100dvh] justify-center bg-black">
      <main className="flex min-h-[100dvh] w-full max-w-[460px] flex-col bg-page px-5 pb-8 pt-10 shadow-2xl">
        <div className="enter mx-auto flex w-full max-w-md flex-1 flex-col md:flex-none">
          <div className="surface flex flex-1 flex-col p-6 md:flex-none md:p-9">
            <Wordmark size="lg" />
            {feito ? (
              <>
                <h1 className="mt-6 flex items-center gap-2 text-2xl text-ink">
                  <CheckCircle2 size={24} className="text-pos" /> Senha alterada
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Por segurança, todas as sessões abertas foram encerradas. Entre com a senha nova e
                  o seu rosto.
                </p>
                <Link to="/login" className="btn btn-ink mt-6 w-full">
                  Entrar
                </Link>
              </>
            ) : etapa ? (
              <>
                <h1 className="mt-6 text-2xl text-ink">Agora, o seu rosto</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Para trocar a senha, confirme que é você: olhe para a câmera e faça o que a tela
                  pedir. São mais passos que no login.
                </p>
                {erro && (
                  <div className="mt-4">
                    <ErrorBox>{erro}</ErrorBox>
                  </div>
                )}
                <button
                  className="btn btn-ink mt-6 w-full gap-2"
                  disabled={loading}
                  onClick={() => setCamera(true)}
                >
                  <ScanFace size={20} /> {loading ? "Conferindo…" : "Verificar meu rosto"}
                </button>
                <button
                  className="btn btn-ghost mt-3 w-full"
                  disabled={loading}
                  onClick={() => recomecar(null)}
                >
                  Voltar
                </button>
              </>
            ) : (
              <>
                <h1 className="mt-6 text-2xl text-ink">Esqueci minha senha</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Você cria uma senha nova e confirma com o seu rosto. Não enviamos link por e-mail
                  ou SMS.
                </p>
                <form onSubmit={continuar} className="mt-7 space-y-4">
                  <Field label="Conta" id="login" hint="E-mail ou CPF.">
                    <input
                      id="login"
                      autoComplete="username"
                      className="field"
                      value={login}
                      onChange={(e) => setLogin(e.target.value)}
                      placeholder="voce@email.com"
                    />
                  </Field>
                  <Field label="Data de nascimento" id="nascimento">
                    <input
                      id="nascimento"
                      type="date"
                      autoComplete="bday"
                      className="field"
                      value={nascimento}
                      onChange={(e) => setNascimento(e.target.value)}
                    />
                  </Field>
                  <Field label="Senha nova" id="senha" hint="Ao menos 10 caracteres.">
                    <input
                      id="senha"
                      type="password"
                      autoComplete="new-password"
                      className="field"
                      value={senha}
                      onChange={(e) => setSenha(e.target.value)}
                    />
                  </Field>
                  <Field label="Repita a senha nova" id="repetida">
                    <input
                      id="repetida"
                      type="password"
                      autoComplete="new-password"
                      className="field"
                      value={repetida}
                      onChange={(e) => setRepetida(e.target.value)}
                    />
                  </Field>
                  {erro && <ErrorBox>{erro}</ErrorBox>}
                  <button className="btn btn-ink w-full" disabled={loading}>
                    {loading ? "Conferindo…" : "Continuar"}
                  </button>
                </form>
              </>
            )}

            {!feito && (
              <p className="mt-auto pt-7 text-center text-sm text-muted-foreground md:mt-7">
                Lembrou?{" "}
                <Link to="/login" className="font-semibold text-ink underline underline-offset-4">
                  Entrar
                </Link>
              </p>
            )}
          </div>
        </div>

        {etapa && camera && (
          <LivenessCheck
            desafio={etapa.desafio}
            onClose={() => setCamera(false)}
            onSuccess={(prova) => {
              setCamera(false);
              setLoading(true);
              concluirRecuperacao(etapa, prova, senha)
                .then(() => setFeito(true))
                // O token e o desafio são de uso único: qualquer recusa recomeça do zero.
                .catch((err: Error) => recomecar(err.message))
                .finally(() => setLoading(false));
            }}
          />
        )}
      </main>
    </div>
  );
}
