import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Check,
  ClipboardPaste,
  Copy,
  FileText,
  KeyRound,
  QrCode,
  SlidersHorizontal,
} from "lucide-react";
import { criarChave, minhasChaves } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Empty, ErrorBox, PageTitle } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/pix")({
  head: () => ({ meta: [{ title: "Pix — PayFlow" }] }),
  component: Pix,
});

const ROTULO_CHAVE: Record<string, string> = {
  cpf: "CPF",
  cnpj: "CNPJ",
  email: "E-mail",
  celular: "Celular",
  aleatoria: "Chave aleatória",
};

function Pix() {
  const { conta } = useAuth();
  const ehPJ = conta?.tipo === "PJ";
  const [aba, setAba] = useState<"receber" | "chaves">("receber");

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Transferências e cobranças na hora, 24h, sem tarifa.">Área Pix</PageTitle>

      {/* Ações */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <AcaoPix icon={ArrowUpRight} label="Enviar" to="/transferir" />
        <AcaoPix icon={ArrowDownLeft} label="Receber" onClick={() => setAba("receber")} />
        {ehPJ ? (
          <AcaoPix icon={FileText} label="Cobrar" to="/contas" />
        ) : (
          <AcaoPix icon={QrCode} label="Pagar QR" to="/transferir" />
        )}
        <AcaoPix icon={SlidersHorizontal} label="Limites" to="/config" />
      </div>

      {/* Colar código */}
      <ColaCodigo />

      {/* Abas: receber / chaves */}
      <div role="tablist" className="grid grid-cols-2 rounded-full bg-tint p-1">
        {(["receber", "chaves"] as const).map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={aba === d}
            onClick={() => setAba(d)}
            className={cn(
              "h-10 rounded-full text-sm font-semibold transition-colors",
              aba === d ? "bg-card text-ink shadow-soft" : "text-mut2 hover:text-ink",
            )}
          >
            {d === "receber" ? "Receber" : "Minhas chaves"}
          </button>
        ))}
      </div>

      {aba === "receber" ? <Receber ehPJ={ehPJ} /> : <Chaves ehPJ={ehPJ} />}
    </div>
  );
}

function AcaoPix({
  icon: Icon,
  label,
  to,
  onClick,
}: {
  icon: typeof QrCode;
  label: string;
  to?: string;
  onClick?: () => void;
}) {
  const inner = (
    <>
      <span className="grid h-12 w-12 place-items-center rounded-full bg-ink text-ink-foreground">
        <Icon size={20} />
      </span>
      <span className="text-sm font-medium text-ink">{label}</span>
    </>
  );
  const klass =
    "surface flex flex-col items-center gap-2 p-4 transition hover:-translate-y-0.5 hover:shadow-lift";
  return to ? (
    <Link to={to} className={klass}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={klass}>
      {inner}
    </button>
  );
}

function ColaCodigo() {
  const nav = useNavigate();
  const [codigo, setCodigo] = useState("");
  return (
    <section className="surface p-5">
      <h2 className="flex items-center gap-2 text-lg text-ink">
        <ClipboardPaste size={18} /> Pix copia e cola
      </h2>
      <p className="mt-1 text-sm text-mut3">Cole um código Pix para pagar.</p>
      <div className="mt-3 flex gap-2">
        <input
          className="field flex-1"
          placeholder="Cole o código aqui"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
        />
        <button
          className="btn btn-ink px-5"
          disabled={!codigo.trim()}
          onClick={() => nav({ to: "/transferir" })}
        >
          Pagar
        </button>
      </div>
    </section>
  );
}

function Receber({ ehPJ }: { ehPJ: boolean }) {
  const { conta } = useAuth();
  const q = useQuery({ queryKey: ["chaves"], queryFn: minhasChaves });
  const [copiado, setCopiado] = useState(false);
  const chave = q.data?.[0];

  async function copiar(txt: string) {
    try {
      await navigator.clipboard.writeText(txt);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* clipboard bloqueado: a chave continua visível */
    }
  }

  return (
    <section className="surface flex flex-col items-center p-6 text-center">
      <h2 className="self-start text-lg text-ink">Receber com Pix</h2>
      <p className="mt-1 self-start text-sm text-mut3">
        Mostre o QR Code ou compartilhe sua chave. Transferências recebidas não têm imposto.
      </p>

      <div className="mt-5 rounded-[20px] border border-border bg-background p-4">
        <FakeQR seed={chave?.valor ?? conta?.numero ?? "payflow"} />
      </div>
      <p className="mt-3 font-semibold text-ink">{conta?.nome}</p>
      <p className="text-xs text-mut3">
        {ehPJ ? "Conta empresa" : "Conta pessoal"} · ag {conta?.agencia ?? "0001"} · c/{" "}
        {conta?.numero}
      </p>

      {chave && (
        <div className="mt-4 flex w-full items-center gap-2 rounded-[14px] bg-tint p-3">
          <div className="min-w-0 flex-1 text-left">
            <p className="text-[11px] uppercase tracking-wide text-mut3">
              {ROTULO_CHAVE[chave.tipo] ?? chave.tipo}
            </p>
            <p className="truncate font-mono text-sm text-ink">{chave.valor}</p>
          </div>
          <button
            className="btn btn-ghost h-9 gap-1 px-3 text-sm"
            onClick={() => copiar(chave.valor)}
          >
            {copiado ? <Check size={14} /> : <Copy size={14} />} {copiado ? "Copiado" : "Copiar"}
          </button>
        </div>
      )}
    </section>
  );
}

function Chaves({ ehPJ }: { ehPJ: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["chaves"], queryFn: minhasChaves });
  const mut = useMutation({
    mutationFn: (tipo: string) => criarChave(tipo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chaves"] }),
  });
  const tipoDoc = ehPJ ? "cnpj" : "cpf";
  const temDoc = q.data?.some((k) => k.tipo === tipoDoc);
  const limite = ehPJ ? 20 : 5;

  return (
    <section className="surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg text-ink">
          <KeyRound size={18} /> Minhas chaves
        </h2>
        <span className="text-xs text-mut3">
          {q.data?.length ?? 0}/{limite}
        </span>
      </div>

      {q.isLoading ? (
        <div className="mt-4 space-y-2">
          {[0, 1].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-tint" />
          ))}
        </div>
      ) : q.data?.length ? (
        <ul className="mt-3 divide-y divide-border">
          {q.data.map((k) => (
            <li key={k.id} className="flex items-center justify-between gap-3 py-3">
              <span className="flex items-center gap-2 text-sm text-mut2">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-tint text-ink">
                  <KeyRound size={15} />
                </span>
                {ROTULO_CHAVE[k.tipo] ?? k.tipo}
              </span>
              <span className="truncate font-mono text-xs text-ink">{k.valor}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty title="Nenhuma chave ainda" hint="Crie uma chave para receber Pix." />
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {!temDoc && (
          <button
            className="btn btn-ghost h-9 text-sm"
            disabled={mut.isPending}
            onClick={() => mut.mutate(tipoDoc)}
          >
            Usar meu {ehPJ ? "CNPJ" : "CPF"}
          </button>
        )}
        <button
          className="btn btn-ghost h-9 text-sm"
          disabled={mut.isPending}
          onClick={() => mut.mutate("email")}
        >
          Cadastrar e-mail
        </button>
        <button
          className="btn btn-ghost h-9 text-sm"
          disabled={mut.isPending}
          onClick={() => mut.mutate("aleatoria")}
        >
          Criar chave aleatória
        </button>
      </div>
      {mut.isError && (
        <div className="mt-3">
          <ErrorBox>{(mut.error as Error).message}</ErrorBox>
        </div>
      )}
    </section>
  );
}

/** QR Code estilizado (não funcional) gerado de forma determinística a partir de uma seed. */
function FakeQR({ seed }: { seed: string }) {
  const n = 21;
  // Hash simples e determinístico para preencher a matriz.
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const rand = (i: number) => {
    let x = (h ^ (i * 2654435761)) >>> 0;
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return ((x >>> 0) % 100) / 100;
  };
  const isFinder = (r: number, c: number) => {
    const inBox = (r0: number, c0: number) => r >= r0 && r < r0 + 7 && c >= c0 && c < c0 + 7;
    return inBox(0, 0) || inBox(0, n - 7) || inBox(n - 7, 0);
  };
  const finderOn = (r: number, c: number) => {
    const rel = (r0: number, c0: number) => {
      const rr = r - r0;
      const cc = c - c0;
      const edge = rr === 0 || rr === 6 || cc === 0 || cc === 6;
      const core = rr >= 2 && rr <= 4 && cc >= 2 && cc <= 4;
      return edge || core;
    };
    if (r < 7 && c < 7) return rel(0, 0);
    if (r < 7 && c >= n - 7) return rel(0, n - 7);
    if (r >= n - 7 && c < 7) return rel(n - 7, 0);
    return false;
  };
  const cells: boolean[] = [];
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      cells.push(isFinder(r, c) ? finderOn(r, c) : rand(r * n + c) > 0.55);
    }
  }
  return (
    <div
      aria-label="QR Code Pix"
      role="img"
      className="grid h-44 w-44"
      style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}
    >
      {cells.map((on, i) => (
        <span key={i} className={on ? "bg-ink" : "bg-transparent"} />
      ))}
    </div>
  );
}
