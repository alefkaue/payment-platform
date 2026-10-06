import { useEffect, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";

/**
 * Verificação facial com PROVA DE VIDA (liveness) — feita DENTRO do app, pela
 * câmera ao vivo, não por foto. Usa o FaceLandmarker (MediaPipe) para detectar
 * desafios aleatórios (piscar, virar o rosto). O vídeo nunca sai do dispositivo
 * e nenhuma imagem é enviada/salva — só o resultado (passou/não passou).
 *
 * No webview do apk (Capacitor) exige a permissão CAMERA no AndroidManifest.
 */

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODELO =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

type DesafioId = "piscar" | "esquerda" | "direita";
const TEXTO: Record<DesafioId, string> = {
  piscar: "Pisque os dois olhos",
  esquerda: "Vire o rosto para a esquerda",
  direita: "Vire o rosto para a direita",
};

type Fase = "carregando" | "ativo" | "ok" | "erro";

export function LivenessCheck({
  onSuccess,
  onClose,
}: {
  onSuccess: () => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [fase, setFase] = useState<Fase>("carregando");
  const [erro, setErro] = useState<string | null>(null);
  const [passo, setPasso] = useState(0);
  const [temRosto, setTemRosto] = useState(false);

  // Sequência de desafios aleatória (sempre começa pelo piscar).
  const desafiosRef = useRef<DesafioId[]>(
    Math.random() > 0.5 ? ["piscar", "esquerda", "direita"] : ["piscar", "direita", "esquerda"],
  );
  const desafios = desafiosRef.current;

  useEffect(() => {
    let parar = false;
    let stream: MediaStream | null = null;
    let landmarker: import("@mediapipe/tasks-vision").FaceLandmarker | null = null;
    let raf = 0;
    let olhosAbertosAntes = false; // para exigir "fechar depois de aberto" no piscar

    async function iniciar() {
      try {
        const vision = await import("@mediapipe/tasks-vision");
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM);
        landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODELO, delegate: "GPU" },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: true,
          outputFacialTransformationMatrixes: true,
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
            : "Não foi possível iniciar a câmera neste dispositivo.",
        );
        setFase("erro");
      }
    }

    function loop() {
      const v = videoRef.current;
      if (parar || !landmarker || !v || v.readyState < 2) {
        raf = requestAnimationFrame(loop);
        return;
      }
      const r = landmarker.detectForVideo(v, performance.now());
      const temFace = !!r.faceLandmarks?.length;
      setTemRosto(temFace);

      if (temFace) {
        const bs = r.faceBlendshapes?.[0]?.categories ?? [];
        const val = (name: string) => bs.find((c) => c.categoryName === name)?.score ?? 0;
        const piscou = val("eyeBlinkLeft") > 0.45 && val("eyeBlinkRight") > 0.45;
        if (val("eyeBlinkLeft") < 0.2 && val("eyeBlinkRight") < 0.2) olhosAbertosAntes = true;

        // Yaw (virar) a partir dos landmarks: nariz vs. laterais do rosto.
        const lm = r.faceLandmarks[0]!;
        const nariz = lm[1];
        const ladoE = lm[234];
        const ladoD = lm[454];
        let yaw = 0;
        if (nariz && ladoE && ladoD) {
          const meio = (ladoE.x + ladoD.x) / 2;
          const largura = Math.abs(ladoD.x - ladoE.x) || 1;
          yaw = (nariz.x - meio) / largura; // >0 e <0 conforme o lado
        }

        const atual = desafios[passo];
        let cumpriu = false;
        if (atual === "piscar") cumpriu = olhosAbertosAntes && piscou;
        else if (atual === "esquerda") cumpriu = yaw > 0.12;
        else if (atual === "direita") cumpriu = yaw < -0.12;

        if (cumpriu) {
          olhosAbertosAntes = false;
          if (passo + 1 >= desafios.length) {
            setFase("ok");
            setPasso(desafios.length);
            setTimeout(() => {
              if (!parar) onSuccess();
            }, 900);
            return; // para o loop
          }
          setPasso((p) => p + 1);
        }
      }
      raf = requestAnimationFrame(loop);
    }

    iniciar();
    return () => {
      parar = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      landmarker?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passo]);

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
        {/* Moldura oval */}
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

      {/* Desafio atual + progresso */}
      <div className="mt-7 px-6 text-center">
        {fase === "erro" ? (
          <>
            <p className="text-ink-foreground/80">{erro}</p>
            <button onClick={onClose} className="btn btn-glass mt-5 w-full">
              Fechar
            </button>
          </>
        ) : fase === "ok" ? (
          <p className="text-lg font-semibold text-pos">Rosto confirmado!</p>
        ) : (
          <>
            <p className="text-xl font-semibold">
              {TEXTO[desafios[Math.min(passo, desafios.length - 1)]!]}
            </p>
            <p className="mt-2 text-sm text-ink-foreground/60">
              {temRosto ? "Siga a instrução acima" : "Posicione o rosto dentro do oval"}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              {desafios.map((d, i) => (
                <span
                  key={d}
                  className={`h-1.5 w-8 rounded-full ${i < passo ? "bg-pos" : i === passo ? "bg-marca" : "bg-ink-foreground/20"}`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <p className="mt-auto px-6 pb-8 pt-6 text-center text-xs text-ink-foreground/45">
        A imagem é processada no seu aparelho e não é armazenada.
      </p>
    </div>
  );
}
