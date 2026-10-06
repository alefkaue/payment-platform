import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Abertura do app: a moeda (dourada) gira, o nome "payflow" sai de dentro dela,
 * a moeda vira o "o" do payfl[o]w, depois volta a girar e o app abre.
 * Mostra uma vez por sessão (cada cold-open do apk/aba).
 */
export function SplashIntro({ onDone }: { onDone: () => void }) {
  const [fase, setFase] = useState(0); // 0 girando · 1 nome sai · 2 segura · 3 volta a girar/fecha

  useEffect(() => {
    const ts = [
      window.setTimeout(() => setFase(1), 1000),
      window.setTimeout(() => setFase(2), 1750),
      window.setTimeout(() => setFase(3), 2500),
      window.setTimeout(() => onDone(), 3200),
    ];
    return () => ts.forEach(clearTimeout);
  }, [onDone]);

  const girando = fase === 0 || fase === 3;
  const nomeVisivel = fase === 1 || fase === 2;
  const moedaGrande = fase === 0 || fase === 3;

  return (
    <div
      className={cn(
        "fixed inset-0 z-[100] flex items-center justify-center bg-ink transition-opacity duration-500",
        fase === 3 ? "opacity-0" : "opacity-100",
      )}
      aria-hidden
    >
      <style>{`@keyframes pfspin{to{transform:rotateY(360deg)}}`}</style>
      <div className="flex items-center" style={{ perspective: "700px" }}>
        <span
          className={cn(
            "text-4xl font-bold tracking-display text-ink-foreground transition-all duration-500 md:text-5xl",
            nomeVisivel ? "translate-x-0 opacity-100" : "translate-x-5 opacity-0",
          )}
        >
          payfl
        </span>
        <span
          className="mx-[0.06em] inline-block shrink-0 rounded-full bg-marca transition-all duration-500"
          style={{
            width: moedaGrande ? 72 : 24,
            height: moedaGrande ? 72 : 24,
            animation: girando ? "pfspin 0.85s linear infinite" : "none",
            boxShadow: "0 10px 34px -6px rgba(212,175,55,0.65)",
          }}
        />
        <span
          className={cn(
            "text-4xl font-bold tracking-display text-ink-foreground transition-all duration-500 md:text-5xl",
            nomeVisivel ? "translate-x-0 opacity-100" : "-translate-x-5 opacity-0",
          )}
        >
          w
        </span>
      </div>
    </div>
  );
}
