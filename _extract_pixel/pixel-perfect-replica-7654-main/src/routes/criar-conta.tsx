import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { registrar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { maskDoc } from "@/lib/format";
import { ErrorBox, Field, SelfieCapture, Wordmark } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/criar-conta")({
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

function CriarConta() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const [tipo, setTipo] = useState<"PF" | "PJ">("PF");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [doc, setDoc] = useState("");
  const [selfie, setSelfie] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const digits = doc.replace(/\D/g, "");
    if (!nome || !email) return setErro("Preencha nome e e-mail.");
    if (senha.length < 8) return setErro("A senha precisa ter ao menos 8 caracteres.");
    if (digits.length !== (tipo === "PF" ? 11 : 14))
      return setErro(`${tipo === "PF" ? "CPF" : "CNPJ"} incompleto.`);
    if (!selfie) return setErro("Envie a selfie de cadastro.");
    setLoading(true);
    try {
      const r = await registrar({ tipo, nome, email, senha, documento: digits, selfie });
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
            <SelfieCapture value={selfie} onChange={setSelfie} />
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
    </main>
  );
}
