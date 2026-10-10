import { TEXTO_DEMONSTRACAO } from "@/lib/split-fase";
import type { SplitFase } from "@/lib/types";

export function SplitAviso({ fase }: { fase: SplitFase | undefined }) {
  if (fase !== "demonstracao") return null;
  return (
    <div className="my-3 text-sm text-pending">
      <span className="inline-flex rounded-full bg-tint px-3 py-1 font-semibold">Simulação</span>
      <p className="mt-2">{TEXTO_DEMONSTRACAO}</p>
    </div>
  );
}
