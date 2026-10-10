import { createFileRoute, Link } from "@tanstack/react-router";
import { Plane, ShieldCheck, ShoppingBag, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { PageTitle } from "@/components/payflow/ui";
import { CartaoSection } from "./_app.config";

export const Route = createFileRoute("/_app/cartoes")({
  head: () => ({ meta: [{ title: "Cartões — Astro" }] }),
  component: Cartoes,
});

function Cartoes() {
  const { conta } = useAuth();
  const ehPJ = conta?.tipo === "PJ";

  return (
    <div className="enter space-y-7">
      <PageTitle
        sub={
          ehPJ
            ? "Cartão corporativo virtual, com travas e CVV dinâmico."
            : "Cartão virtual, com travas de segurança e CVV dinâmico."
        }
      >
        Cartões
      </PageTitle>

      <CartaoSection />

      <section className="surface p-6">
        <h2 className="text-lg text-ink">Por que é mais seguro</h2>
        <ul className="mt-4 space-y-3 text-sm text-mut2">
          <Beneficio
            icon={<ShieldCheck size={18} />}
            titulo="CVV dinâmico"
            desc="O código de segurança muda a cada janela de tempo — não adianta ser copiado."
          />
          <Beneficio
            icon={<Sparkles size={18} />}
            titulo="100% digital"
            desc="Sem plástico. Adicione à carteira do celular e pague por aproximação."
          />
          {!ehPJ && (
            <>
              <Beneficio
                icon={<ShoppingBag size={18} />}
                titulo="Trava de compras online"
                desc="Ligue só quando for usar e congele o cartão na hora pelo app."
              />
              <Beneficio
                icon={<Plane size={18} />}
                titulo="Compras internacionais"
                desc="Ative quando viajar; desligue depois para reduzir risco."
              />
            </>
          )}
        </ul>
      </section>
    </div>
  );
}

function Beneficio({
  icon,
  titulo,
  desc,
}: {
  icon: React.ReactNode;
  titulo: string;
  desc: string;
}) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-tint text-ink">
        {icon}
      </span>
      <span>
        <span className="block font-medium text-ink">{titulo}</span>
        <span className="block text-mut3">{desc}</span>
      </span>
    </li>
  );
}
