import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Check, ScanFace } from "lucide-react";
import { concluirCadastro, MODO_API, novoDesafioLogin, registrar } from "@/lib/api";
import { PORTES, REGIMES_APURACAO } from "@/lib/empresa";
import { useAuth } from "@/lib/auth";
import { maskDoc } from "@/lib/format";
import type {
  CadastroResposta,
  EmpresaPayload,
  PortePJ,
  ProvaBiometrica,
  RegimeApuracao,
  TipoDocumentoEmpresa,
  TipoDocumentoPessoa,
} from "@/lib/types";
import { ErrorBox, Field, Wordmark } from "@/components/payflow/ui";
import { LivenessCheck } from "@/components/payflow/liveness";
import { CampoDocumento } from "@/components/payflow/documento";
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

const DOCS_PESSOA: Record<TipoDocumentoPessoa, string> = {
  rg: "RG",
  cnh: "CNH",
  cin: "Carteira de Identidade Nacional (CIN)",
  passaporte: "Passaporte",
};
const DOCS_EMPRESA: Record<TipoDocumentoEmpresa, string> = {
  contrato_social: "Contrato social",
  ccmei: "CCMEI (certificado do MEI)",
  cartao_cnpj: "Cartão CNPJ",
  procuracao: "Procuração",
  outro: "Outro",
};

/**
 * Abertura de conta com KYC: dados da pessoa + documento de identidade (foto) +
 * prova de vida de cadastro. Na PJ, quem abre é a pessoa que vai operar a
 * empresa (o banco confere que ela está no quadro de sócios) e entra também o
 * documento societário. Depois de criada, a conta pede o 2º fator do login (o
 * rosto) e só então a empresa é aberta, já com a pessoa logada.
 */
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
  const [nascimento, setNascimento] = useState("");
  const [celular, setCelular] = useState("");
  const [tipoDoc, setTipoDoc] = useState<TipoDocumentoPessoa>("cnh");
  const [frente, setFrente] = useState<string | null>(null);
  const [verso, setVerso] = useState<string | null>(null);
  const [setor, setSetor] = useState(SETORES[0] ?? "Indústria");
  const [porte, setPorte] = useState<PortePJ>("PME");
  const [regime, setRegime] = useState<RegimeApuracao>("regular");
  const [tipoDocEmpresa, setTipoDocEmpresa] = useState<TipoDocumentoEmpresa>("contrato_social");
  const [docEmpresa, setDocEmpresa] = useState<string | null>(null);
  const [prova, setProva] = useState<{ p: ProvaBiometrica; em: number } | null>(null);
  const [liveness, setLiveness] = useState<null | "cadastro" | "login">(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Conta criada: falta o rosto do primeiro login.
  const [criado, setCriado] = useState<CadastroResposta | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaPayload | undefined>(undefined);
  const [erroEmpresa, setErroEmpresa] = useState<string | null>(null);

  const facialOk = prova !== null && Date.now() - prova.em < VALIDADE_PROVA_MS;
  // No servidor o documento é obrigatório; na demonstração dá para pular.
  const docObrigatorio = MODO_API;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const digits = doc.replace(/\D/g, "");
    if (!nome || !email) return setErro("Preencha nome e e-mail.");
    if (senha.length < 10) return setErro("A senha precisa ter ao menos 10 caracteres.");
    if (digits.length !== (tipo === "PF" ? 11 : 14))
      return setErro(`${tipo === "PF" ? "CPF" : "CNPJ"} incompleto.`);
    if (tipo === "PJ" && (!representante || cpf.replace(/\D/g, "").length !== 11))
      return setErro("Informe o nome e o CPF de quem vai operar a conta da empresa.");
    if (!nascimento) return setErro("Informe a data de nascimento.");
    if (celular.replace(/\D/g, "").length < 10) return setErro("Informe um celular com DDD.");
    if (docObrigatorio && !frente) return setErro("Envie a foto do documento de identidade.");
    if (tipo === "PJ" && docObrigatorio && !docEmpresa)
      return setErro("Envie o documento da empresa (contrato social, CCMEI ou cartão CNPJ).");
    if (!prova || !facialOk)
      return setErro(
        prova
          ? "A verificação facial expirou. Faça de novo."
          : "Conclua a verificação facial (prova de vida).",
      );
    setLoading(true);
    try {
      const pj: EmpresaPayload | undefined =
        tipo === "PJ"
          ? {
              cnpj: digits,
              nome_fantasia: nome,
              porte,
              regime_apuracao: porte === "MEI" ? "mei" : regime,
              setor,
              ...(docEmpresa
                ? { documentos: [{ tipo: tipoDocEmpresa, arquivo: docEmpresa }] }
                : {}),
            }
          : undefined;
      const r = await registrar({
        nome: tipo === "PF" ? nome : representante,
        email,
        senha,
        cpf: tipo === "PF" ? digits : cpf.replace(/\D/g, ""),
        data_nascimento: nascimento,
        celular: celular.replace(/\D/g, ""),
        documento: frente ? { tipo: tipoDoc, frente, ...(verso ? { verso } : {}) } : null,
        biometria: prova.p,
        ...(pj ? { empresa: pj } : {}),
      });
      setEmpresa(pj);
      setCriado(r);
      setLiveness("login");
    } catch (err) {
      setErro((err as Error).message);
      setProva(null); // o desafio foi consumido: uma nova tentativa precisa de outra verificação
    } finally {
      setLoading(false);
    }
  }

  async function entrarComRosto(p: ProvaBiometrica) {
    if (!criado) return;
    setLoading(true);
    setErro(null);
    try {
      const r = await concluirCadastro(criado.etapa, p, empresa);
      entrar(r.resposta);
      if (r.erroEmpresa) setErroEmpresa(r.erroEmpresa);
      else nav({ to: "/inicio" });
    } catch (err) {
      setErro((err as Error).message);
      // o desafio é de uso único: prepara outro para a próxima tentativa
      novoDesafioLogin(criado.etapa)
        .then((etapa) => setCriado({ ...criado, etapa }))
        .catch(() => nav({ to: "/login" }));
    } finally {
      setLoading(false);
    }
  }

  if (criado)
    return (
      <div className="flex min-h-[100dvh] justify-center bg-black">
        <main className="min-h-[100dvh] w-full max-w-[460px] bg-page px-4 py-10 shadow-2xl">
          <div className="enter surface mx-auto w-full max-w-lg p-6 md:p-10">
            <Wordmark />
            <span className="mt-6 grid h-12 w-12 place-items-center rounded-full bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos">
              <Check size={26} strokeWidth={3} />
            </span>
            <h1 className="mt-4 text-2xl text-ink">Conta criada</h1>
            <KycAviso status={criado.kyc.status} motivos={criado.kyc.motivos} />
            {erroEmpresa ? (
              <>
                <div className="mt-4">
                  <ErrorBox>
                    Sua conta pessoal está pronta, mas a empresa não foi aberta: {erroEmpresa}
                  </ErrorBox>
                </div>
                <button className="btn btn-ink mt-6 w-full" onClick={() => nav({ to: "/inicio" })}>
                  Ir para a conta pessoal
                </button>
              </>
            ) : (
              <>
                <p className="mt-3 text-sm text-muted-foreground">
                  Agora entre pela primeira vez: confirme seu rosto (siga os passos que a tela
                  pedir).
                  {empresa && " Em seguida abrimos a conta da empresa."}
                </p>
                {erro && (
                  <div className="mt-4">
                    <ErrorBox>{erro}</ErrorBox>
                  </div>
                )}
                <button
                  className="btn btn-ink mt-6 w-full gap-2"
                  disabled={loading}
                  onClick={() => setLiveness("login")}
                >
                  <ScanFace size={20} /> {loading ? "Entrando…" : "Entrar com o rosto"}
                </button>
              </>
            )}
          </div>
          {liveness === "login" && !erroEmpresa && (
            <LivenessCheck
              desafio={criado.etapa.desafio}
              onClose={() => setLiveness(null)}
              onSuccess={(p) => {
                setLiveness(null);
                void entrarComRosto(p);
              }}
            />
          )}
        </main>
      </div>
    );

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
              <Field label={tipo === "PF" ? "Nome completo" : "Razão social"} id="nome">
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
                  autoComplete="email"
                  className="field"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field
                label="Senha"
                id="senha"
                hint="Mínimo de 10 caracteres. Uma frase curta é ótima; evite senhas comuns, seu nome ou CPF."
              >
                <input
                  id="senha"
                  type="password"
                  autoComplete="new-password"
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
                    hint="Define as regras de acesso da equipe e de aprovação."
                  >
                    <select
                      id="porte"
                      className="field"
                      value={porte}
                      onChange={(e) => {
                        const p = e.target.value as PortePJ;
                        setPorte(p);
                        setTipoDocEmpresa(p === "MEI" ? "ccmei" : "contrato_social");
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
                  <Field label="Documento da empresa" id="tipo-doc-empresa">
                    <select
                      id="tipo-doc-empresa"
                      className="field"
                      value={tipoDocEmpresa}
                      onChange={(e) => setTipoDocEmpresa(e.target.value as TipoDocumentoEmpresa)}
                    >
                      {(["contrato_social", "ccmei", "cartao_cnpj"] as const).map((t) => (
                        <option key={t} value={t}>
                          {DOCS_EMPRESA[t]}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <CampoDocumento
                    rotulo={DOCS_EMPRESA[tipoDocEmpresa]}
                    dica="PDF ou foto legível, até 10 MB. Conferimos o CNPJ no documento."
                    valor={docEmpresa}
                    onChange={setDocEmpresa}
                    aceitaPdf
                    maxMb={10}
                  />
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Seu nome (sócio)" id="rep">
                      <input
                        id="rep"
                        className="field"
                        value={representante}
                        onChange={(e) => setRepresentante(e.target.value)}
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
                  </div>
                  <p className="-mt-1 text-xs text-mut3">
                    Você vai operar a conta com o seu próprio login. Outras pessoas (sócios,
                    financeiro, contador) entram depois em Equipe, cada uma com o próprio acesso.
                  </p>
                </>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Data de nascimento" id="nasc">
                  <input
                    id="nasc"
                    type="date"
                    className="field"
                    value={nascimento}
                    onChange={(e) => setNascimento(e.target.value)}
                  />
                </Field>
                <Field label="Celular" id="cel">
                  <input
                    id="cel"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel-national"
                    className="field tabular"
                    value={celular}
                    onChange={(e) => setCelular(e.target.value)}
                    placeholder="(11) 98765-4321"
                  />
                </Field>
              </div>

              <Field label="Seu documento com foto" id="tipo-doc">
                <select
                  id="tipo-doc"
                  className="field"
                  value={tipoDoc}
                  onChange={(e) => setTipoDoc(e.target.value as TipoDocumentoPessoa)}
                >
                  {(Object.keys(DOCS_PESSOA) as TipoDocumentoPessoa[]).map((t) => (
                    <option key={t} value={t}>
                      {DOCS_PESSOA[t]}
                    </option>
                  ))}
                </select>
              </Field>
              <CampoDocumento
                rotulo={`${DOCS_PESSOA[tipoDoc]} — frente`}
                dica={
                  docObrigatorio
                    ? "Foto nítida, sem reflexo, com o documento inteiro. Conferimos CPF, nome e o rosto com a sua selfie."
                    : "Demonstração: opcional."
                }
                valor={frente}
                onChange={setFrente}
              />
              {tipoDoc !== "passaporte" && (
                <CampoDocumento
                  rotulo={`${DOCS_PESSOA[tipoDoc]} — verso (opcional)`}
                  valor={verso}
                  onChange={setVerso}
                />
              )}

              <FacialStep ok={facialOk} onStart={() => setLiveness("cadastro")} />
              {erro && <ErrorBox>{erro}</ErrorBox>}
              <button className="btn btn-ink w-full" disabled={loading}>
                {loading ? "Conferindo seus dados…" : "Criar conta"}
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

        {liveness === "cadastro" && (
          <LivenessCheck
            modo="cadastro"
            onClose={() => setLiveness(null)}
            onSuccess={(p) => {
              setLiveness(null);
              setProva({ p, em: Date.now() });
            }}
          />
        )}
      </main>
    </div>
  );
}

function KycAviso({ status, motivos }: { status: string; motivos: string[] }) {
  if (status === "aprovado") return <p className="mt-2 text-sm text-pos">Identidade confirmada.</p>;
  if (status === "em_analise")
    return (
      <div className="mt-2 text-sm text-muted-foreground">
        <p>
          Seu documento foi para análise de uma pessoa da nossa equipe. Você já pode entrar; abrir
          empresa e algumas operações ficam disponíveis assim que a análise terminar.
        </p>
        {motivos.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-mut3">
            {motivos.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
      </div>
    );
  return null;
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
            Pela câmera, ao vivo: piscar, sorrir e virar o rosto, na ordem que a tela pedir.
            Guardamos só um código do rosto, criptografado.
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
