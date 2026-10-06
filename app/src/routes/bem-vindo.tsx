import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Wordmark } from "@/components/payflow/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/bem-vindo")({
  head: () => ({
    meta: [
      { title: "PayFlow — seu banco digital" },
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
    <main className="relative h-[100dvh] w-full overflow-hidden bg-ink text-white">
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

      {/* Marca + título */}
      <div className="absolute inset-x-0 top-0 z-20 px-6 pt-8">
        <Wordmark tone="light" size="sm" />
        <h1 className="mt-6 max-w-[14ch] text-[2rem] font-semibold leading-[1.12] tracking-display drop-shadow-[0_2px_12px_rgba(0,0,0,0.5)]">
          {SLIDES[i]?.title}
        </h1>
      </div>

      {/* Ações */}
      <div className="absolute inset-x-0 bottom-0 z-20 px-5 pb-10">
        <Link
          to="/login"
          className="flex h-14 w-full items-center justify-center rounded-full bg-white text-base font-semibold text-ink shadow-[0_12px_32px_-8px_rgba(0,0,0,0.5)] transition active:scale-[0.99]"
        >
          Entrar ou criar conta
        </Link>
        <Link
          to="/login"
          className="mt-4 block text-center text-sm font-medium text-white/90 hover:text-white"
        >
          Preciso de ajuda
        </Link>
      </div>
    </main>
  );
}
