import { useId, useState } from "react";
import { Camera, Check, FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Foto/arquivo de documento (KYC da pessoa e KYB da empresa).
 *
 * - Imagem: reduzida no aparelho para no máx. 1600 px no lado maior, JPEG 0,9
 *   (mantém o texto legível para o OCR e fica bem abaixo do limite do servidor).
 * - PDF (só onde `aceitaPdf`): vai como está, até `maxMb`.
 * O servidor confere o tipo pelos bytes, recusa PDF com script e não guarda a
 * imagem (só o hash e os campos conferidos).
 */

const LADO_MAX = 1600;

function lerComoDataUrl(arquivo: Blob): Promise<string> {
  return new Promise((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result));
    r.onerror = () => falha(new Error("Não foi possível ler o arquivo."));
    r.readAsDataURL(arquivo);
  });
}

async function reduzirImagem(arquivo: File): Promise<string> {
  const url = URL.createObjectURL(arquivo);
  try {
    const img = await new Promise<HTMLImageElement>((ok, falha) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => falha(new Error("Imagem inválida. Tire outra foto."));
      i.src = url;
    });
    const escala = Math.min(1, LADO_MAX / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * escala);
    c.height = Math.round(img.naturalHeight * escala);
    c.getContext("2d")?.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.9);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function prepararArquivo(
  arquivo: File,
  { aceitaPdf = false, maxMb = 6 }: { aceitaPdf?: boolean; maxMb?: number } = {},
): Promise<string> {
  if (arquivo.type === "application/pdf") {
    if (!aceitaPdf) throw new Error("Envie uma foto (JPG ou PNG) do documento.");
    if (arquivo.size > maxMb * 1024 * 1024)
      throw new Error(`O PDF passa de ${maxMb} MB. Gere uma versão menor.`);
    return lerComoDataUrl(arquivo);
  }
  if (!arquivo.type.startsWith("image/")) throw new Error("Tipo de arquivo não aceito.");
  return reduzirImagem(arquivo);
}

export function CampoDocumento({
  rotulo,
  dica,
  valor,
  onChange,
  aceitaPdf = false,
  maxMb,
}: {
  rotulo: string;
  dica?: string;
  valor: string | null;
  onChange: (dataUrl: string | null) => void;
  aceitaPdf?: boolean;
  maxMb?: number;
}) {
  const id = useId();
  const [erro, setErro] = useState<string | null>(null);
  const [lendo, setLendo] = useState(false);
  const ehPdf = valor?.startsWith("data:application/pdf");

  return (
    <div className="rounded-[18px] border border-dashed border-line2 bg-background p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-xl",
            valor
              ? "bg-[color-mix(in_oklab,var(--pos)_16%,transparent)] text-pos"
              : "bg-tint text-ink",
          )}
        >
          {lendo ? (
            <Loader2 size={20} className="animate-spin" />
          ) : valor && !ehPdf ? (
            <img src={valor} alt="" className="h-full w-full object-cover" />
          ) : valor ? (
            <FileText size={20} />
          ) : (
            <Camera size={20} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 font-medium text-ink">
            {rotulo} {valor && <Check size={16} className="text-pos" strokeWidth={3} />}
          </p>
          {dica && <p className="mt-0.5 text-sm text-muted-foreground">{dica}</p>}
          <label
            htmlFor={id}
            className="mt-2 inline-block cursor-pointer text-sm font-semibold text-ink underline underline-offset-4"
          >
            {valor ? "Trocar" : aceitaPdf ? "Enviar arquivo ou foto" : "Tirar foto ou escolher"}
          </label>
          {valor && (
            <button
              type="button"
              className="ml-4 text-sm text-mut3 underline underline-offset-4"
              onClick={() => onChange(null)}
            >
              Remover
            </button>
          )}
          <input
            id={id}
            type="file"
            className="sr-only"
            accept={aceitaPdf ? "application/pdf,image/*" : "image/*"}
            {...(aceitaPdf ? {} : { capture: "environment" as const })}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              setErro(null);
              setLendo(true);
              prepararArquivo(f, { aceitaPdf, ...(maxMb ? { maxMb } : {}) })
                .then(onChange)
                .catch((err: Error) => setErro(err.message))
                .finally(() => setLendo(false));
            }}
          />
          {erro && <p className="mt-2 text-sm text-err">{erro}</p>}
        </div>
      </div>
    </div>
  );
}
