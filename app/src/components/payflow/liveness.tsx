import { useEffect, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { pedirDesafio } from "@/lib/api";
import type { Desafio, ProvaBiometrica } from "@/lib/types";

/**
 * Verificação facial com prova de vida, guiada por um DESAFIO DO SERVIDOR.
 *
 * 1. Pede o desafio (POST /biometria/desafios): ação sorteada + validade, uso único.
 * 2. Com a câmera ao vivo e o FaceLandmarker (MediaPipe), guia a pessoa: primeiro
 *    de frente, depois virando o rosto para o lado pedido.
 * 3. Captura os quadros nesses momentos (sem espelhamento) e devolve a prova
 *    {desafio_id, quadros}. QUEM DECIDE é o servidor: ele confere o desafio, faz
 *    anti-spoofing, mede o giro e compara o rosto. A checagem daqui só guia.
 *
 * No webview do apk (Capacitor) exige a permissão CAMERA no AndroidManifest.
 */

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODELO =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

type Passo = "frente" | "esquerda" | "direita";
const TEXTO: Record<Passo, string> = {
  frente: "Olhe de frente para a câmera",
  esquerda: "Agora vire devagar o rosto para a sua esquerda",
  direita: "Agora vire devagar o rosto para a sua direita",
};
// Limiares do guia (o servidor tem os dele). yaw > 0 = nariz à direita da imagem
// sem espelho = pessoa virando para a esquerda dela.
const FRONTAL = 0.05;
const GIRO = 0.12;

type Fase = "carregando" | "ativo" | "ok" | "erro";

function capturar(v: HTMLVideoElement): string {
  const escala = Math.min(1, 480 / (v.videoWidth || 480));
  const c = document.createElement("canvas");
  c.width = Math.round((v.videoWidth || 480) * escala);
  c.height = Math.round((v.videoHeight || 640) * escala);
  c.getContext("2d")?.drawImage(v, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.85);
}

export function LivenessCheck({
  onSuccess,
  onClose,
}: {
  onSuccess: (prova: ProvaBiometrica) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [fase, setFase] = useState<Fase>("carregando");
  const [erro, setErro] = useState<string | null>(null);
  const [desafio, setDesafio] = useState<Desafio | null>(null);
  const [passoIdx, setPassoIdx] = useState(0);
  const [temRosto, setTemRosto] = useState(false);
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const passos: Passo[] = desafio
    ? ["frente", desafio.acao === "virar_esquerda" ? "esquerda" : "direita"]
    : ["frente"];

  useEffect(() => {
    let parar = false;
    let stream: MediaStream | null = null;
    let landmarker: import("@mediapipe/tasks-vision").FaceLandmarker | null = null;
    let raf = 0;
    let passo = 0;
    let roteiro: Passo[] = ["frente"];
    let ultimoDesafio: Desafio | null = null;
    const quadros: string[] = [];

    async function iniciar() {
      try {
        ultimoDesafio = await pedirDesafio();
        if (parar) return;
        setDesafio(ultimoDesafio);
        roteiro = ["frente", ultimoDesafio.acao === "virar_esquerda" ? "esquerda" : "direita"];

        const vision = await import("@mediapipe/tasks-vision");
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM);
        landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODELO, delegate: "GPU" },
          runningMode: "VIDEO",
          numFaces: 1,
        });
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: 480, height: 640 },
          audio: false,
        });
        if (parar) return;
        const v = videoRef.current;
        if (!v) return;
        v.srcObject = stream;
        await v.play();
        setFase("ativo");
        loop();
      } catch (e) {
        if (parar) return;
        const msg = (e as Error)?.message ?? "";
        setErro(
          /denied|permission|NotAllowed/i.test(msg)
            ? "Precisamos da câmera para a verificação. Permita o acesso e tente de novo."
            : msg && !/getUserMedia|camera/i.test(msg)
              ? msg
              : "Não foi possível iniciar a câmera neste dispositivo.",
        );
        setFase("erro");
      }
    }

    function loop() {
      const v = videoRef.current;
      if (parar) return;
      if (!landmarker || !v || v.readyState < 2) {
        raf = requestAnimationFrame(loop);
        return;
      }
      const r = landmarker.detectForVideo(v, performance.now());
      const lm = r.faceLandmarks?.[0];
      setTemRosto(Boolean(lm));
      if (lm) {
        const nariz = lm[1];
        const ladoE = lm[234];
        const ladoD = lm[454];
        let yaw = 0;
        if (nariz && ladoE && ladoD) {
          const meio = (ladoE.x + ladoD.x) / 2;
          yaw = (nariz.x - meio) / (Math.abs(ladoD.x - ladoE.x) || 1);
        }
        const atual = roteiro[passo];
        const cumpriu =
          atual === "frente"
            ? Math.abs(yaw) < FRONTAL
            : atual === "esquerda"
              ? yaw > GIRO
              : yaw < -GIRO;
        if (cumpriu) {
          quadros.push(capturar(v));
          if (atual !== "frente") quadros.push(capturar(v));
          passo += 1;
          setPassoIdx(passo);
          if (passo >= roteiro.length && ultimoDesafio) {
            setFase("ok");
            const prova = { desafio_id: ultimoDesafio.desafio_id, quadros: quadros.slice(0, 5) };
            setTimeout(() => {
              if (!parar) onSuccessRef.current(prova);
            }, 700);
            return;
          }
        }
      }
      raf = requestAnimationFrame(loop);
    }

    void iniciar();
    return () => {
      parar = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      landmarker?.close();
    };
  }, []);

  const atual = passos[Math.min(passoIdx, passos.length - 1)] ?? "frente";

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink text-ink-foreground">
      <div className="flex items-center justify-between px-5 pt-6">
        <p className="font-semibold">Verificação facial</p>
        <button aria-label="Fechar" onClick={onClose} className="text-ink-foreground/70">
          <X size={22} />
        </button>
      </div>

      <div className="relative mx-auto mt-4 aspect-[3/4] w-[min(86%,340px)] overflow-hidden rounded-[28px] bg-black ring-1 ring-ink-foreground/10">
        <video
          ref={videoRef}
          muted
          playsInline
          className="h-full w-full -scale-x-100 object-cover"
        />
        <div
          className={`pointer-events-none absolute inset-6 rounded-[50%] border-2 transition-colors ${
            fase === "ok" ? "border-pos" : temRosto ? "border-marca" : "border-ink-foreground/30"
          }`}
        />
        {fase === "carregando" && (
          <div className="absolute inset-0 grid place-items-center bg-black/40 text-sm">
            <span className="flex items-center gap-2">
              <Loader2 className="animate-spin" size={18} /> Preparando a câmera…
            </span>
          </div>
        )}
        {fase === "ok" && (
          <div className="absolute inset-0 grid place-items-center bg-black/50">
            <span className="grid h-16 w-16 place-items-center rounded-full bg-pos text-ink-foreground">
              <Check size={32} strokeWidth={3} />
            </span>
          </div>
        )}
      </div>

      <div className="mt-7 px-6 text-center">
        {fase === "erro" ? (
          <>
            <p className="text-ink-foreground/80">{erro}</p>
            <button onClick={onClose} className="btn btn-glass mt-5 w-full">
              Fechar
            </button>
          </>
        ) : fase === "ok" ? (
          <p className="text-lg font-semibold text-pos">Pronto! Conferindo com o banco…</p>
        ) : (
          <>
            <p className="text-xl font-semibold">{TEXTO[atual]}</p>
            <p className="mt-2 text-sm text-ink-foreground/60">
              {temRosto ? "Siga a instrução acima" : "Posicione o rosto dentro do oval"}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              {passos.map((p, i) => (
                <span
                  key={p}
                  className={`h-1.5 w-8 rounded-full ${i < passoIdx ? "bg-pos" : i === passoIdx ? "bg-marca" : "bg-ink-foreground/20"}`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <p className="mt-auto px-6 pb-8 pt-6 text-center text-xs text-ink-foreground/45">
        Enviamos alguns quadros só para esta verificação. Eles não são guardados: o banco mantém
        apenas um código matemático do seu rosto, criptografado.
      </p>
    </div>
  );
}
