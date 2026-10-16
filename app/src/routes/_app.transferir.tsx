import { useFecharAoVoltar, BotaoFinanceiro } from "@/lib/mobile";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Clock, KeyRound } from "lucide-react";
import {
  consultarCobranca,
  consultarDestino,
  LIMITE_AUTENTICACAO_ADICIONAL,
  pagarCobranca,
  pedeTotp,
  transferir,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtBRL, parseValor } from "@/lib/format";
import type { CarteiraInfo, Cobranca, ConfirmacaoPagamento } from "@/lib/types";
import { ErrorBox, Field, PageTitle, ValueRow } from "@/components/payflow/ui";
import { ConfirmarPagamento } from "@/components/payflow/confirmar-pagamento";
import { criarIntencaoPagamento } from "@/lib/intencao-pagamento";

export const Route = createFileRoute("/_app/transferir")({
  head: () => ({
    meta: [
      { title: "Transferir — Astro" },
      {
        name: "description",
        content:
          "Pix por chave ou conta, confirmado com a sua senha (e código do autenticador em valores altos).",
      },
      { property: "og:title", content: "Transferir — Astro" },
      { property: "og:description", content: "Pix por chave ou conta." },
    ],
  }),
  component: Transferir,
});

/**
 * Pix/transferência. Transferência NÃO tem split: imposto só é retido quando você
 * paga uma cobrança com nota fiscal. Toda transferência é confirmada com a senha;
 * acima de R$ 5.000 também com o código do app autenticador (TOTP). Em conta de
 * empresa, acima da sua alçada a operação vai para aprovação.
 */
function Transferir() {
  const { conta } = useAuth();
  return <TransferirConta key={conta?.carteira_id} />;
}

function TransferirConta() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { conta } = useAuth();
  const [destino, setDestino] = useState("");
  const [valorStr, setValorStr] = useState("");
  const [info, setInfo] = useState<CarteiraInfo | null>(null);
  useFecharAoVoltar(info, () => {
    setInfo(null);
    setErro(null);
  });
  const [confirmando, setConfirmando] = useState(false);
  const [pendente, setPendente] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const enviando = useRef(false);
  const ativo = useRef(true);
  useEffect(() => {
    ativo.current = true;
    return () => {
      ativo.current = false;
    };
  }, []);
  const [intencao] = useState(criarIntencaoPagamento);
  const [chave, setChave] = useState("");
  const [modoCobranca, setModoCobranca] = useState(false);
  const [cobranca, setCobranca] = useState<Cobranca | null>(null);

  const valor = parseValor(valorStr);
  const acimaDaAlcada = conta?.tipo === "PJ" && conta.alcada != null && valor > conta.alcada;
  const precisaTotp = pedeTotp(valor) && !acimaDaAlcada;

  async function revisar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!destino.trim()) return setErro("Informe a chave Pix ou o número da conta.");
    if (!modoCobranca && !(valor > 0)) return setErro("Informe um valor válido.");
    setLoading(true);
    try {
      if (modoCobranca) {
        const c = await consultarCobranca(destino.trim());
        if (c.status !== "aberta") throw new Error("Esta cobrança não está aberta.");
        setCobranca(c);
        setValorStr(c.valor.toFixed(2).replace(".", ","));
        setInfo({
          carteira_id: c.recebedor_carteira_id ?? 0,
          nome: c.recebedor_nome ?? "Recebedor",
          tipo: "PJ",
        });
        setChave(
          intencao.preparar(JSON.stringify([conta?.carteira_id, "cobranca", c.txid, c.valor])),
        );
      } else {
        const d = await consultarDestino(destino);
        setCobranca(null);
        setInfo(d);
        setChave(intencao.preparar(JSON.stringify([conta?.carteira_id, d.destino, valor])));
      }
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  /** Erros aparecem na própria janela de confirmação (senha/código), que segue aberta. */
  async function enviar(confirmacao: ConfirmacaoPagamento) {
    if (enviando.current || !info || (!info.destino && !cobranca)) return;
    enviando.current = true;
    setErro(null);
    setLoading(true);
    try {
      const r = cobranca
        ? await pagarCobranca(cobranca.txid, chave, confirmacao)
        : await transferir({
            destino: info.destino!,
            valor,
            confirmacao,
            idempotency_key: chave,
          });
      intencao.concluir();
      if (!ativo.current) return;
      setConfirmando(false);
      setInfo(null);
      qc.invalidateQueries();
      if (r.tipo === "pendente") setPendente(r.mensagem);
      else nav({ to: "/comprovante/$id", params: { id: String(r.transacao.id) } });
    } finally {
      enviando.current = false;
      setLoading(false);
    }
  }

  if (conta?.tipo === "PJ" && conta.papel === "consulta")
    return (
      <div className="enter mx-auto max-w-md text-center">
        <h1 className="text-2xl text-ink">Acesso só de consulta</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Seu papel nesta empresa permite ver saldo e extrato, mas não movimentar. Para pagar, peça
          a um administrador para alterar seu acesso.
        </p>
        <Link to="/inicio" className="btn btn-ink mt-6 w-full">
          Voltar ao início
        </Link>
      </div>
    );

  if (pendente)
    return (
      <div className="enter mx-auto max-w-md text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-tax-bg text-tax2">
          <Clock size={28} />
        </div>
        <h1 className="mt-5 text-2xl text-ink">Enviado para aprovação</h1>
        <p className="mt-2 text-sm text-muted-foreground">{pendente}</p>
        <Link to="/inicio" className="btn btn-ink mt-6 w-full">
          Voltar ao início
        </Link>
      </div>
    );

  return (
    <div className="enter">
      <PageTitle sub="Por chave Pix (CPF, CNPJ, e-mail, celular ou aleatória) ou número da conta.">
        Transferir
      </PageTitle>

      {!info ? (
        <form onSubmit={revisar} className="surface space-y-4 p-5 md:p-7">
          <label className="flex gap-2 text-sm text-mut2">
            <input
              type="checkbox"
              checked={modoCobranca}
              disabled={loading}
              onChange={(e) => setModoCobranca(e.target.checked)}
            />
            Pagar cobrança pelo identificador (txid)
          </label>
          <Field
            label={modoCobranca ? "Identificador da cobrança (txid)" : "Chave Pix ou conta"}
            id="destino"
            hint={
              modoCobranca
                ? "Informe o identificador recebido de quem cobra."
                : "Ex.: e-mail, CPF ou 12345678-9."
            }
          >
            <input
              id="destino"
              className="field"
              value={destino}
              disabled={loading}
              onChange={(e) => setDestino(e.target.value)}
              placeholder="Chave Pix ou número da conta"
            />
          </Field>
          {!modoCobranca && (
            <Field label="Valor (R$)" id="valor">
              <input
                autoComplete="off"
                id="valor"
                inputMode="decimal"
                className="field tabular text-lg"
                value={valorStr}
                disabled={loading}
                onChange={(e) => setValorStr(e.target.value)}
                placeholder="0,00"
              />
            </Field>
          )}
          {erro && <ErrorBox>{erro}</ErrorBox>}
          <BotaoFinanceiro className="btn btn-ink w-full" disabled={loading}>
            {loading ? "Consultando…" : "Revisar"}
          </BotaoFinanceiro>
        </form>
      ) : (
        <div className="space-y-4">
          <section className="surface enter p-5 md:p-7">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">Para</p>
                <p className="truncate text-lg font-semibold text-ink">{info.nome}</p>
                {info.documento && <p className="text-xs text-mut3">{info.documento}</p>}
              </div>
              <span className="shrink-0 rounded-full bg-tint px-3 py-1 text-xs font-semibold text-mut2">
                {info.tipo === "PJ" ? "Empresa" : "Pessoa física"}
              </span>
            </div>
            <div className="mt-5 divide-y divide-border">
              <ValueRow label="Valor" value={valor} strong />
            </div>
            {cobranca ? (
              <p className="mt-3 text-sm text-mut2">
                O valor e os impostos da cobrança são conferidos pelo servidor.
              </p>
            ) : (
              <p className="mt-3 rounded-[14px] bg-tint px-4 py-3 text-sm text-mut2">
                Transferência não tem retenção de imposto: {info.nome} recebe {fmtBRL(valor)}.
                {info.tipo === "PJ" &&
                  " Se for a compra de um produto ou serviço, peça a cobrança da empresa: aí a CBS e o IBS da nota são separados no pagamento."}
              </p>
            )}
            {acimaDaAlcada && (
              <p className="mt-3 rounded-[14px] bg-tax-bg px-4 py-3 text-sm text-tax2">
                Acima da sua alçada ({fmtBRL(conta?.alcada ?? 0)}): a transferência vai para
                aprovação de outra pessoa da empresa.
              </p>
            )}
            <p className="mt-3 flex items-center gap-2 text-sm text-mut2">
              <KeyRound size={16} className="shrink-0" />
              {precisaTotp
                ? `Acima de ${fmtBRL(LIMITE_AUTENTICACAO_ADICIONAL)}: confirme com a senha e o código do app autenticador.`
                : "Você confirma com a senha da sua conta."}
            </p>
          </section>

          {erro && <ErrorBox>{erro}</ErrorBox>}
          <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
            <button
              className="btn btn-ghost"
              disabled={loading}
              onClick={() => {
                setInfo(null);
                setErro(null);
              }}
            >
              Voltar
            </button>
            <BotaoFinanceiro
              className="btn btn-ink"
              onClick={() => setConfirmando(true)}
              disabled={loading}
            >
              {loading
                ? "Enviando…"
                : acimaDaAlcada
                  ? "Enviar para aprovação"
                  : cobranca
                    ? "Confirmar pagamento"
                    : "Confirmar transferência"}
            </BotaoFinanceiro>
          </div>
        </div>
      )}

      {confirmando && (
        <ConfirmarPagamento
          valor={valor}
          pedeTotp={precisaTotp}
          titulo={cobranca ? "Confirme o pagamento" : "Confirme a transferência"}
          acao={acimaDaAlcada ? "Enviar para aprovação" : "Confirmar"}
          onClose={() => setConfirmando(false)}
          onConfirmar={enviar}
        />
      )}
    </div>
  );
}
