import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Check, Copy, KeyRound, ShieldCheck } from "lucide-react";
import { encode } from "uqr";
import {
  confirmarTotp,
  iniciarTotp,
  LIMITE_AUTENTICACAO_ADICIONAL,
  temTotp,
  type AtivacaoTotp,
} from "@/lib/api";
import { fmtBRL } from "@/lib/format";
import { ErrorBox, Field } from "./ui";

/** QR Code em SVG (sem innerHTML): um retângulo por módulo escuro, numa linha só. */
export function QrCode({ texto, tamanho = 196 }: { texto: string; tamanho?: number }) {
  const { d, lado } = useMemo(() => {
    const qr = encode(texto, { border: 2 });
    let caminho = "";
    qr.data.forEach((linha, y) =>
      linha.forEach((escuro, x) => {
        if (escuro) caminho += `M${x} ${y}h1v1h-1z`;
      }),
    );
    return { d: caminho, lado: qr.size };
  }, [texto]);
  return (
    <svg
      role="img"
      aria-label="QR Code para o app autenticador"
      viewBox={`0 0 ${lado} ${lado}`}
      width={tamanho}
      height={tamanho}
      shapeRendering="crispEdges"
      className="rounded-[12px] bg-white"
    >
      <path d={d} fill="#000" />
    </svg>
  );
}

const emGrupos = (s: string) => s.replace(/(.{4})/g, "$1 ").trim();

/**
 * Verificação em duas etapas (TOTP): pagamentos acima do limite pedem o código do
 * app autenticador (Google Authenticator, Microsoft Authenticator, Authy...).
 * Ativação: POST /auth/totp (segredo + QR) e POST /auth/totp/confirmar (1º código).
 */
export function SegundoFator() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["totp"], queryFn: temTotp });
  const [ativacao, setAtivacao] = useState<AtivacaoTotp | null>(null);
  const [codigo, setCodigo] = useState("");
  const [copiado, setCopiado] = useState(false);
  const [trocar, setTrocar] = useState(false);
  const iniciar = useMutation({
    mutationFn: iniciarTotp,
    onSuccess: (a) => {
      setAtivacao(a);
      setTrocar(false);
      setCodigo("");
      // Começar de novo desliga o anterior até confirmar (como no servidor).
      void qc.invalidateQueries({ queryKey: ["totp"] });
    },
  });
  const confirmar = useMutation({
    mutationFn: () => confirmarTotp(codigo),
    onSuccess: () => {
      setAtivacao(null);
      setCodigo("");
      void qc.invalidateQueries({ queryKey: ["totp"] });
    },
    onError: () => setCodigo(""),
  });
  const ocupado = iniciar.isPending || confirmar.isPending;

  async function copiar(segredo: string) {
    try {
      await navigator.clipboard.writeText(segredo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* sem permissão de área de transferência: o segredo continua visível */
    }
  }

  return (
    <section className="surface space-y-4 p-5" aria-labelledby="totp-titulo">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-tint text-ink">
          <KeyRound size={19} />
        </span>
        <div className="min-w-0">
          <h2 id="totp-titulo" className="text-lg text-ink">
            Verificação em duas etapas
          </h2>
          <p className="text-sm text-mut2">
            Todo pagamento é confirmado com a sua senha. Acima de{" "}
            {fmtBRL(LIMITE_AUTENTICACAO_ADICIONAL)}, também com o código de um app autenticador.
          </p>
        </div>
      </div>

      {status.isPending ? (
        <p role="status" className="text-sm text-mut3">
          Consultando…
        </p>
      ) : status.isError ? (
        <ErrorBox>Não foi possível consultar a verificação em duas etapas.</ErrorBox>
      ) : ativacao ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ocupado) confirmar.mutate();
          }}
        >
          <ol className="list-decimal space-y-1 pl-5 text-sm text-mut2">
            <li>Abra o app autenticador e escolha adicionar conta.</li>
            <li>Leia o QR Code (ou digite a chave abaixo).</li>
            <li>Digite o código de 6 dígitos que aparecer.</li>
          </ol>
          <div className="flex justify-center">
            <QrCode texto={ativacao.uri} />
          </div>
          <div className="rounded-[14px] bg-tint px-4 py-3">
            <p className="text-xs text-mut3">Chave para digitar</p>
            <div className="mt-1 flex items-center justify-between gap-3">
              <code className="break-all font-mono text-sm text-ink">
                {emGrupos(ativacao.segredo)}
              </code>
              <button
                type="button"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line2 text-mut2"
                aria-label="Copiar chave"
                onClick={() => void copiar(ativacao.segredo)}
              >
                {copiado ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          </div>
          <a href={ativacao.uri} className="btn btn-ghost w-full">
            Abrir no app autenticador deste celular
          </a>
          <Field label="Código de 6 dígitos" id="totp-codigo">
            <input
              id="totp-codigo"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              className="field tabular tracking-[0.4em]"
              placeholder="000000"
              value={codigo}
              disabled={ocupado}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
            />
          </Field>
          {confirmar.isError && <ErrorBox>{confirmar.error.message}</ErrorBox>}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={ocupado}
              onClick={() => {
                setAtivacao(null);
                confirmar.reset();
              }}
            >
              Cancelar
            </button>
            <button className="btn btn-ink" disabled={ocupado || codigo.length !== 6}>
              {confirmar.isPending ? "Conferindo…" : "Ativar"}
            </button>
          </div>
        </form>
      ) : status.data ? (
        <>
          <p className="flex items-center gap-2 text-sm font-medium text-pos">
            <ShieldCheck size={16} /> Ativa neste perfil.
          </p>
          {trocar ? (
            <div
              className="rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2"
              aria-live="polite"
            >
              <p>
                O app autenticador atual deixa de valer assim que você começar. Até confirmar o
                novo, pagamentos acima de {fmtBRL(LIMITE_AUTENTICACAO_ADICIONAL)} ficam bloqueados.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <button
                  className="btn btn-ghost"
                  disabled={ocupado}
                  onClick={() => setTrocar(false)}
                >
                  Cancelar
                </button>
                <button className="btn btn-ink" disabled={ocupado} onClick={() => iniciar.mutate()}>
                  {iniciar.isPending ? "Gerando…" : "Continuar"}
                </button>
              </div>
            </div>
          ) : (
            <button className="btn btn-ghost w-full" onClick={() => setTrocar(true)}>
              Trocar de app autenticador
            </button>
          )}
        </>
      ) : (
        <button
          className="btn btn-ink w-full gap-2"
          disabled={ocupado}
          onClick={() => iniciar.mutate()}
        >
          <ShieldCheck size={18} /> {iniciar.isPending ? "Gerando…" : "Ativar agora"}
        </button>
      )}
      {iniciar.isError && <ErrorBox>{iniciar.error.message}</ErrorBox>}
    </section>
  );
}
