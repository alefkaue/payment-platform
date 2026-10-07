import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ChevronDown, LifeBuoy, Mail, MessageCircle, Split } from "lucide-react";
import { PageTitle } from "@/components/payflow/ui";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/ajuda")({
  head: () => ({ meta: [{ title: "Ajuda — Astro" }] }),
  component: Ajuda,
});

const FAQS: [string, string][] = [
  [
    "O que é o split de IBS/CBS?",
    "É a divisão do pagamento prevista na Reforma (LC 214/2025): quando um cliente paga uma venda com nota fiscal, o banco separa a CBS e o IBS destacados na nota e envia ao Fisco; a empresa recebe o líquido. Transferência comum não tem split.",
  ],
  [
    "Transferência que eu faço tem imposto?",
    "Não. Pix e transferências entre contas (inclusive para empresas) nunca sofrem retenção. O split só acontece no pagamento de uma venda com nota fiscal.",
  ],
  [
    "Como o dinheiro da conta rende?",
    "O saldo rende automaticamente, sem você precisar aplicar. O rendimento aparece no seu extrato.",
  ],
  [
    "O cartão virtual é seguro para compras online?",
    "Sim. Ele tem CVV dinâmico (muda a cada janela de tempo), travas de compras online e internacionais, e você pode congelá-lo na hora pelas Configurações.",
  ],
  [
    "Como minha empresa controla quem movimenta a conta?",
    "Cada pessoa tem um papel (administrador, aprovador, operador ou só consulta) e uma alçada em reais. Pagamentos acima da alçada de quem lançou ficam pendentes até um segundo aprovador confirmar.",
  ],
  [
    "As alíquotas do split são reais?",
    "Seguem a transição da Reforma: 2026 é ano-teste (0,9% + 0,1%); 2027–2028 a CBS fica cheia e o IBS segue baixo; o IBS sobe aos poucos até o regime pleno (≈26,5%) em 2033. As alíquotas de referência ainda serão fixadas oficialmente.",
  ],
];

function Ajuda() {
  const { conta } = useAuth();
  const [aberta, setAberta] = useState<number | null>(0);

  return (
    <div className="enter space-y-7">
      <PageTitle sub="Tire suas dúvidas ou fale com a gente.">Ajuda</PageTitle>

      {/* Canais */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Canal icon={<MessageCircle size={20} />} titulo="Chat" desc="Resposta em minutos" />
        <Canal icon={<Mail size={20} />} titulo="E-mail" desc="ajuda@astro.com.br" />
        <Canal icon={<LifeBuoy size={20} />} titulo="Central 24h" desc="0800 000 0000" />
      </div>

      {/* Destaque split */}
      {conta?.tipo === "PJ" && (
        <Link
          to="/split"
          className="surface flex items-center gap-4 p-5 transition hover:-translate-y-0.5 hover:shadow-lift"
        >
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-tax-bg text-tax2">
            <Split size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-ink">Entenda o split da Reforma</p>
            <p className="text-sm text-mut3">O imposto separado no ato, explicado passo a passo.</p>
          </div>
        </Link>
      )}

      {/* FAQ */}
      <section>
        <h2 className="mb-3 text-lg text-ink">Perguntas frequentes</h2>
        <div className="surface divide-y divide-border overflow-hidden">
          {FAQS.map(([q, a], i) => {
            const open = aberta === i;
            return (
              <div key={q}>
                <button
                  onClick={() => setAberta(open ? null : i)}
                  aria-expanded={open}
                  className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
                >
                  <span className="font-medium text-ink">{q}</span>
                  <ChevronDown
                    size={18}
                    className={cn("shrink-0 text-mut3 transition-transform", open && "rotate-180")}
                  />
                </button>
                {open && <p className="px-5 pb-4 text-sm leading-relaxed text-mut2">{a}</p>}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function Canal({ icon, titulo, desc }: { icon: React.ReactNode; titulo: string; desc: string }) {
  return (
    <div className="surface flex flex-col gap-1 p-5">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-tint text-ink">
        {icon}
      </span>
      <p className="mt-2 font-semibold text-ink">{titulo}</p>
      <p className="text-sm text-mut3">{desc}</p>
    </div>
  );
}
