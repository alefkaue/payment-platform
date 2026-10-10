import { useId } from "react";
import type { TipoDocumentoPessoa } from "@/lib/types";
import { Field } from "./ui";
import { CampoDocumento } from "./documento";

const DOCUMENTOS: Record<TipoDocumentoPessoa, string> = {
  rg: "RG",
  cnh: "CNH",
  cin: "Carteira de Identidade Nacional (CIN)",
  passaporte: "Passaporte",
};

export function DocumentoPessoa({
  tipo,
  frente,
  verso,
  onTipo,
  onFrente,
  onVerso,
}: {
  tipo: TipoDocumentoPessoa;
  frente: string | null;
  verso: string | null;
  onTipo: (tipo: TipoDocumentoPessoa) => void;
  onFrente: (valor: string | null) => void;
  onVerso: (valor: string | null) => void;
}) {
  const id = useId();
  const precisaVerso = tipo !== "passaporte";
  return (
    <>
      <Field label="Qual documento" id={id}>
        <select
          id={id}
          className="field"
          value={tipo}
          onChange={(e) => onTipo(e.target.value as TipoDocumentoPessoa)}
        >
          {(Object.keys(DOCUMENTOS) as TipoDocumentoPessoa[]).map((t) => (
            <option key={t} value={t}>
              {DOCUMENTOS[t]}
            </option>
          ))}
        </select>
      </Field>
      <CampoDocumento
        rotulo={precisaVerso ? `${DOCUMENTOS[tipo]} — frente` : "Página com a foto"}
        valor={frente}
        onChange={onFrente}
      />
      {precisaVerso && (
        <CampoDocumento rotulo={`${DOCUMENTOS[tipo]} — verso`} valor={verso} onChange={onVerso} />
      )}
    </>
  );
}
