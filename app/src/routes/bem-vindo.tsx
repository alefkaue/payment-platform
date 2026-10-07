import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { HelpCircle } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Wordmark } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/bem-vindo")({
  head: () => ({
    meta: [
      { title: "Astro — seu banco digital" },
      {
        name: "description",
        content: "Conta digital para pessoas e empresas, com o imposto da Reforma resolvido no ato.",
      },
    ],
  }),
  component: BemVindo,
});

const DURACAO = 5000;

const SLIDES = [
  {
    img: "/welcome/pf.jpg",
    title: "Pague no Pix com o imposto já resolvido",
  },
  {
    img: "/welcome/pj.jpg",
    title: "Sua empresa recebe já com o IBS/CBS separado",
  },
  {
    img: "/welcome/vida.jpg",
    title: "Pix grátis, loja e viagens com pontos",
  },
];

function BemVindo() {
  const { ready, conta } = useAuth();
  const [i, setI] = useState(0);

  useEffect(() => {
    const id = setTimeout(() => setI((v) => (v + 1) % SLIDES.length), DURACAO);
    return () => clearTimeout(id);
  }, [i]);

  if (ready && conta) return <Navigate to="/inicio" replace />;

  return (
    <div className="flex min-h-[100dvh] w-full justify-center bg-black">
      <main className="relative mx-auto h-[100dvh] w-full max-w-[460px] overflow-hidden bg-ink text-white shadow-2xl">
        <style>{`@keyframes pfbar{from{transform:scaleX(0)}to{transform:scaleX(1)}}`}</style>

      {/* Fotos em tela cheia (crossfade) */}
      {SLIDES.map((s, idx) => (
        <div
          key={s.img}
          className={cn(
            "absolute inset-0 transition-opacity duration-700",
            idx === i ? "opacity-100" : "opacity-0",
          )}
          aria-hidden={idx !== i}
        >
          <img src={s.img} alt="" className="h-full w-full object-cover" />
        </div>
      ))}
      {/* Véus para legibilidade do texto */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/70 via-black/15 to-black/85" />

      {/* Zonas de toque: esquerda volta, direita avança */}
      <button
        aria-label="Slide anterior"
        className="absolute inset-y-24 left-0 z-10 w-1/3"
        onClick={() => setI((v) => (v - 1 + SLIDES.length) % SLIDES.length)}
      />
      <button
        aria-label="Próximo slide"
        className="absolute inset-y-24 right-0 z-10 w-2/3"
        onClick={() => setI((v) => (v + 1) % SLIDES.length)}
      />

      {/* Barra de progresso estilo stories */}
      <div className="absolute inset-x-0 top-0 z-20 flex gap-1.5 px-4 pt-3">
        {SLIDES.map((s, idx) => (
          <div key={s.img} className="h-[3px] flex-1 overflow-hidden rounded-full bg-white/30">
            <div
              className="h-full w-full origin-left rounded-full bg-white"
              style={
                idx < i
                  ? { transform: "scaleX(1)" }
                  : idx === i
                    ? { animation: `pfbar ${DURACAO}ms linear forwards` }
                    : { transform: "scaleX(0)" }
              }
            />
          </div>
        ))}
      </div>

      {/* Ícone de ajuda (canto superior direito) */}
      <Link
        to="/login"
        aria-label="Ajuda"
        title="Ajuda"
        className="absolute right-5 top-7 z-30 grid h-9 w-9 place-items-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur transition hover:bg-white/20"
      >
        <HelpCircle size={18} />
      </Link>

      {/* Marca + título */}
      <div className="absolute inset-x-0 top-0 z-20 px-6 pt-8">
        <Wordmark tone="light" size="sm" />
        <h1 className="mt-6 max-w-[14ch] text-[2rem] font-semibold leading-[1.12] tracking-display drop-shadow-[0_2px_12px_rgba(0,0,0,0.5)]">
          {SLIDES[i]?.title}
        </h1>
      </div>

      {/* Ações: dois botões separados */}
      <div className="absolute inset-x-0 bottom-0 z-20 space-y-3 px-5 pb-10">
        <Link
          to="/criar-conta"
          className="flex h-14 w-full items-center justify-center rounded-full bg-marca text-base font-semibold text-ink shadow-[0_12px_32px_-8px_rgba(0,0,0,0.5)] transition hover:brightness-95 active:scale-[0.99]"
        >
          Criar conta
        </Link>
        <Link
          to="/login"
          className="flex h-14 w-full items-center justify-center rounded-full border border-white/30 bg-white/10 text-base font-semibold text-white backdrop-blur transition hover:bg-white/20 active:scale-[0.99]"
        >
          Entrar
        </Link>
      </div>
      </main>
    </div>
  );
}
