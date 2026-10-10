import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useFecharAoVoltar } from "@/lib/mobile";
import { useState, type ReactNode } from "react";
import { ArrowLeft, Check, ScanFace } from "lucide-react";
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
import { DocumentoPessoa } from "@/components/payflow/documento-pessoa";
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
    ],
  }),
  component: CriarConta,
});

const SETORES = ["Indústria", "Autopeças", "Comércio", "Serviços", "Transporte", "Outro"];

const DOCS_EMPRESA: Record<TipoDocumentoEmpresa, string> = {
  contrato_social: "Contrato social",
  ccmei: "CCMEI (certificado do MEI)",
  cartao_cnpj: "Cartão CNPJ",
  procuracao: "Procuração",
  outro: "Outro",
};

type Etapa = "dados" | "documento" | "rosto" | "entrar";
const ETAPAS: { id: Etapa; rotulo: string }[] = [
  { id: "dados", rotulo: "Seus dados" },
  { id: "documento", rotulo: "Documento" },
  { id: "rosto", rotulo: "Rosto" },
  { id: "entrar", rotulo: "Entrar" },
];

/**
 * Abertura de conta em ETAPAS, uma tela para cada (SEGURANCA.md item 5):
 *  1. dados da pessoa (e da empresa, na PJ);
 *  2. documento com foto — FRENTE E VERSO obrigatórios (passaporte: só a página
 *     com foto); na PJ também o documento da empresa;
 *  3. rosto (prova de vida de cadastro, com passos sorteados pelo servidor). Ao
 *     concluir, a conta é criada na hora (o desafio vale 2 minutos);
 *  4. primeiro login: o rosto de novo (2º fator) e, na PJ, a abertura da empresa
 *     já com a pessoa logada.
 * O backend confere tudo de novo — a ordem das telas é só para guiar a pessoa.
 */
function CriarConta() {
  const nav = useNavigate();
  const { entrar } = useAuth();
  const { tipo: tipoInicial } = Route.useSearch();
  const [etapa, setEtapa] = useState<Etapa>("dados");
  useFecharAoVoltar(etapa === "documento" || etapa === "rosto", () => {
    setEtapa(etapa === "rosto" ? "documento" : "dados");
  });

  // 1. dados
  const [tipo, setTipo] = useState<"PF" | "PJ">(tipoInicial ?? "PF");
  const [nome, setNome] = useState("");
  const [representante, setRepresentante] = useState("");
  const [cpf, setCpf] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [senha2, setSenha2] = useState("");
  const [doc, setDoc] = useState("");
  const [nascimento, setNascimento] = useState("");
  const [celular, setCelular] = useState("");
  const [setor, setSetor] = useState(SETORES[0] ?? "Indústria");
  const [porte, setPorte] = useState<PortePJ>("PME");
  const [regime, setRegime] = useState<RegimeApuracao>("regular");
  // 2. documento
  const [tipoDoc, setTipoDoc] = useState<TipoDocumentoPessoa>("cnh");
  const [frente, setFrente] = useState<string | null>(null);
  const [verso, setVerso] = useState<string | null>(null);
  const [tipoDocEmpresa, setTipoDocEmpresa] = useState<TipoDocumentoEmpresa>("contrato_social");
  const [docEmpresa, setDocEmpresa] = useState<string | null>(null);
  // 3-4. rosto e entrada
  const [camera, setCamera] = useState<null | "cadastro" | "login">(null);
  const [criado, setCriado] = useState<CadastroResposta | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaPayload | undefined>(undefined);
  const [erroEmpresa, setErroEmpresa] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const digits = doc.replace(/\D/g, "");
  const precisaVerso = tipoDoc !== "passaporte";
  // No servidor o documento é obrigatório; na demonstração dá para pular. Para testar o
  // fluxo sem documento em mãos: `npm run dev` com VITE_DOC_OPCIONAL=1 (e o backend com
  // KYC_DOCUMENTO_OBRIGATORIO=0, que a produção recusa). DEV nunca é true no build.
  const docOpcionalEmTeste = import.meta.env.DEV && import.meta.env["VITE_DOC_OPCIONAL"] === "1";
  const docObrigatorio = MODO_API && !docOpcionalEmTeste;

  function irPara(e: Etapa) {
    setErro(null);
    setEtapa(e);
  }

  function validarDados(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !email.trim()) return setErro("Preencha nome e e-mail.");
    if (senha.length < 10) return setErro("A senha precisa ter ao menos 10 caracteres.");
    if (senha !== senha2) return setErro("As senhas não conferem.");
    if (digits.length !== (tipo === "PF" ? 11 : 14))
      return setErro(`${tipo === "PF" ? "CPF" : "CNPJ"} incompleto.`);
    if (tipo === "PJ" && (!representante.trim() || cpf.replace(/\D/g, "").length !== 11))
      return setErro("Informe o seu nome e o seu CPF (de quem vai operar a conta da empresa).");
    if (!nascimento) return setErro("Informe a data de nascimento.");
    if (celular.replace(/\D/g, "").length < 10) return setErro("Informe um celular com DDD.");
    irPara("documento");
  }

  function validarDocumento(e: React.FormEvent) {
    e.preventDefault();
    if (docObrigatorio && !frente) return setErro("Envie a foto da frente do documento.");
    if (docObrigatorio && precisaVerso && !verso)
      return setErro("Envie a foto do verso do documento.");
    if (frente && precisaVerso && !verso) return setErro("Envie também o verso do documento.");
    if (tipo === "PJ" && docObrigatorio && !docEmpresa)
      return setErro("Envie o documento da empresa (contrato social, CCMEI ou cartão CNPJ).");
    irPara("rosto");
  }

  /** Rosto de cadastro concluído: cria a conta na hora (o desafio vence em 2 min). */
  async function criarConta(prova: ProvaBiometrica) {
    setErro(null);
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
        documento: frente
          ? { tipo: tipoDoc, frente, ...(precisaVerso && verso ? { verso } : {}) }
          : null,
        biometria: prova,
        ...(pj ? { empresa: pj } : {}),
      });
      setEmpresa(pj);
      setCriado(r);
      irPara("entrar");
    } catch (err) {
      // Erro de dados (senha fraca, CPF já usado…): volta para a etapa que resolve.
      const msg = (err as Error).message;
      setErro(msg);
      if (/senha|e-mail|CPF|conta com estes dados|nome|celular|nascimento/i.test(msg))
        setEtapa("dados");
      else if (/documento|verso|imagem|arquivo|identidade/i.test(msg)) setEtapa("documento");
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
        .then((e) => setCriado({ ...criado, etapa: e }))
        .catch(() => nav({ to: "/login" }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] justify-center bg-black">
      <main className="min-h-[100dvh] w-full max-w-[460px] bg-page px-4 py-10 shadow-2xl">
        <div className="enter mx-auto w-full max-w-lg">
          <div className="surface p-6 md:p-10">
            <Wordmark />
            <Progresso atual={etapa} />

            {etapa === "dados" && (
              <form onSubmit={validarDados} className="mt-6 space-y-4">
                <h1 className="text-2xl text-ink">Seus dados</h1>
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
                        "h-10 rounded-full text-sm font-semibold",
                        tipo === t ? "bg-ink text-ink-foreground" : "text-mut2",
                      )}
                    >
                      {t === "PF" ? "Pessoa física" : "Empresa (PJ)"}
                    </button>
                  ))}
                </div>
                <Field label={tipo === "PF" ? "Nome completo" : "Razão social"} id="nome">
                  <input
                    autoComplete="name"
                    id="nome"
                    className="field"
                    value={nome}
                    onChange={(e) => setNome(e.target.value)}
                  />
                </Field>
                <Field label={tipo === "PF" ? "CPF" : "CNPJ"} id="doc">
                  <input
                    autoComplete="off"
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
                    <Field label="Porte da empresa" id="porte">
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
                      <Field label="Regime de apuração" id="regime">
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
                    <Field label="Seu nome (sócio que vai operar a conta)" id="rep">
                      <input
                        autoComplete="name"
                        id="rep"
                        className="field"
                        value={representante}
                        onChange={(e) => setRepresentante(e.target.value)}
                      />
                    </Field>
                    <Field label="Seu CPF" id="cpf">
                      <input
                        autoComplete="off"
                        id="cpf"
                        inputMode="numeric"
                        className="field tabular"
                        value={cpf}
                        onChange={(e) => setCpf(maskDoc(e.target.value, "PF"))}
                        placeholder="000.000.000-00"
                      />
                    </Field>
                  </>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Data de nascimento" id="nasc">
                    <input
                      autoComplete="bday"
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
                <Field label="E-mail" id="email">
                  <input
                    inputMode="email"
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
                  hint="Mínimo de 10 caracteres. Evite senhas comuns, seu nome ou CPF."
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
                <Field label="Repita a senha" id="senha2">
                  <input
                    id="senha2"
                    type="password"
                    autoComplete="new-password"
                    className="field"
                    value={senha2}
                    onChange={(e) => setSenha2(e.target.value)}
                  />
                </Field>
                {erro && <ErrorBox>{erro}</ErrorBox>}
                <button className="btn btn-ink w-full">Continuar</button>
              </form>
            )}

            {etapa === "documento" && (
              <form onSubmit={validarDocumento} className="mt-6 space-y-4">
                <Voltar onClick={() => irPara("dados")} />
                <h1 className="text-2xl text-ink">Documento com foto</h1>
                <p className="text-sm text-muted-foreground">
                  Foto nítida, sem reflexo, com o documento inteiro. Conferimos CPF, nome e o rosto
                  com a sua verificação facial. As imagens não ficam guardadas.
                </p>
                <DocumentoPessoa
                  tipo={tipoDoc}
                  frente={frente}
                  verso={verso}
                  onTipo={setTipoDoc}
                  onFrente={setFrente}
                  onVerso={setVerso}
                />
                {tipo === "PJ" && (
                  <>
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
                  </>
                )}
                {!docObrigatorio && (
                  <p className="text-xs text-mut3">
                    {MODO_API ? "Ambiente de teste" : "Demonstração"}: os documentos são opcionais.
                  </p>
                )}
                {erro && <ErrorBox>{erro}</ErrorBox>}
                <button className="btn btn-ink w-full">Continuar</button>
              </form>
            )}

            {etapa === "rosto" && (
              <div className="mt-6 space-y-4">
                <Voltar onClick={() => irPara("documento")} />
                <h1 className="text-2xl text-ink">Verificação facial</h1>
                <p className="text-sm text-muted-foreground">
                  Pela câmera, ao vivo. A tela vai pedir alguns movimentos (piscar, sorrir, virar o
                  rosto) numa ordem que muda a cada vez: faça só o que for pedido. Guardamos apenas
                  um código do rosto, criptografado.
                </p>
                {erro && <ErrorBox>{erro}</ErrorBox>}
                <button
                  className="btn btn-ink w-full gap-2"
                  disabled={loading}
                  onClick={() => setCamera("cadastro")}
                >
                  <ScanFace size={20} /> {loading ? "Criando a conta…" : "Começar verificação"}
                </button>
              </div>
            )}

            {etapa === "entrar" && criado && (
              <div className="mt-6">
                <span className="grid h-12 w-12 place-items-center rounded-full bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos">
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
                    <button
                      className="btn btn-ink mt-6 w-full"
                      onClick={() => nav({ to: "/inicio" })}
                    >
                      Ir para a conta pessoal
                    </button>
                  </>
                ) : (
                  <>
                    <p className="mt-3 text-sm text-muted-foreground">
                      Agora entre pela primeira vez: confirme o seu rosto mais uma vez.
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
                      onClick={() => setCamera("login")}
                    >
                      <ScanFace size={20} /> {loading ? "Entrando…" : "Entrar com o rosto"}
                    </button>
                  </>
                )}
              </div>
            )}

            {etapa === "dados" && (
              <p className="mt-6 text-center text-sm text-muted-foreground">
                Já tem conta?{" "}
                <Link to="/login" className="font-semibold text-ink underline underline-offset-4">
                  Entrar
                </Link>
              </p>
            )}
          </div>
        </div>

        {camera === "cadastro" && (
          <LivenessCheck
            modo="cadastro"
            onClose={() => setCamera(null)}
            onSuccess={(p) => {
              setCamera(null);
              void criarConta(p);
            }}
          />
        )}
        {camera === "login" && criado && !erroEmpresa && (
          <LivenessCheck
            desafio={criado.etapa.desafio}
            onClose={() => setCamera(null)}
            onSuccess={(p) => {
              setCamera(null);
              void entrarComRosto(p);
            }}
          />
        )}
      </main>
    </div>
  );
}

function Progresso({ atual }: { atual: Etapa }) {
  const idx = ETAPAS.findIndex((e) => e.id === atual);
  return (
    <ol className="mt-6 grid grid-cols-4 gap-2" aria-label="Etapas do cadastro">
      {ETAPAS.map((e, i) => (
        <li key={e.id} aria-current={i === idx ? "step" : undefined}>
          <span
            className={cn(
              "block h-1.5 rounded-full",
              i < idx ? "bg-pos" : i === idx ? "bg-ink" : "bg-line2",
            )}
          />
          <span className={cn("mt-1 block text-[11px]", i === idx ? "text-ink" : "text-mut3")}>
            {e.rotulo}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Voltar({ onClick }: { onClick: () => void }): ReactNode {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-sm text-mut2"
    >
      <ArrowLeft size={16} /> Voltar
    </button>
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
