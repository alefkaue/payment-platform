import { useEffect, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { pedirDesafio } from "@/lib/api";
import type {
  Desafio,
  ModoBiometria,
  PassoBiometria,
  PassoDesafio,
  ProvaBiometrica,
} from "@/lib/types";

/**
 * Verificação facial com prova de vida, guiada por um DESAFIO DO SERVIDOR, agora
 * em VÁRIOS PASSOS.
 *
 * - modo "cadastro": piscar 3x -> sorrir -> virar p/ esquerda -> virar p/ direita.
 * - modo "login": só piscar 3x (mais rápido; no celular normalmente usa a
 *   biometria do aparelho, mas pela câmera o faceless continua).
 *
 * Para cada passo guiamos a pessoa, detectamos o movimento com o FaceLandmarker
 * (MediaPipe) + blendshapes e guardamos os quadros DAQUELE passo (sem
 * espelhamento). No fim mandamos todos juntos. QUEM DECIDE é o servidor: ele
 * reextrai os landmarks, confere a sequência inteira (3 piscadas, sorriso, as 2
 * viradas), com rosto em todos os quadros, faz anti-spoofing e compara o rosto.
 *
 * No webview do apk (Capacitor) exige a permissão CAMERA no AndroidManifest.
 */

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODELO =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Limiares do GUIA (0..1 dos blendshapes; o servidor tem os dele, via EAR/MAR).
const BLINK_FECHADO = 0.5;
const BLINK_ABERTO = 0.2;
const SORRISO_NEUTRO = 0.15;
const SORRISO_ALVO = 0.4;
const YAW_FRONTAL = 0.05;
// Acima do limiar do servidor (0.22) de propósito: garante que os quadros que
// capturamos passem com folga.
const YAW_GIRO = 0.24;
const PISCADAS_EXIGIDAS = 3;
const GIRO_QUADROS = 2;

// Captura ~1 quadro a cada CADENCIA ms, com um teto por passo (soma <= 40).
const CADENCIA_MS = 100;
const CAP: Record<PassoBiometria, number> = {
  piscar3: 24,
  sorrir: 5,
  virar_esquerda: 5,
  virar_direita: 5,
};
// Continua capturando um tiquinho após detectar o passo (pega o "depois").
const POS_MS = 250;

// DEV: desenha onde o rosto é detectado (malha + olhos abrindo/fechando + boca +
// métricas ao vivo). Ajuda de desenvolvimento -- troque para `false` para esconder.
const DEBUG_OVERLAY = true;
const OLHO_ESQ = [362, 385, 387, 263, 373, 380];
const OLHO_DIR = [33, 160, 158, 133, 153, 144];
const BOCA = [61, 13, 291, 14];

type Pt = { x: number; y: number };

function earDe(lm: Pt[], idx: number[]): number {
  const p = idx.map((i) => lm[i]);
  const d = (a?: Pt, b?: Pt) => (a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0);
  const h = d(p[0], p[3]) || 1e-6;
  return (d(p[1], p[5]) + d(p[2], p[4])) / (2 * h);
}

interface Hud {
  passo: string;
  piscadas: number;
  earE: number;
  earD: number;
  smile: number;
  yaw: number;
}

/**
 * Desenha a malha/olhos/boca e as métricas sobre o vídeo. O vídeo aparece
 * espelhado (CSS), então espelhamos só as COORDENADAS dos pontos (x -> 1-x); o
 * texto é desenhado normal, para ficar legível.
 */
function desenharOverlay(
  cv: HTMLCanvasElement,
  video: HTMLVideoElement,
  lm: Pt[] | undefined,
  hud: Hud | null,
) {
  const ctx = cv.getContext("2d");
  if (!ctx) return;
  const W = video.clientWidth || cv.width;
  const H = video.clientHeight || cv.height;
  if (cv.width !== W) cv.width = W;
  if (cv.height !== H) cv.height = H;
  ctx.clearRect(0, 0, W, H);
  if (!lm) return;
  const fx = (x: number) => (1 - x) * W; // espelha p/ casar com o vídeo
  const fy = (y: number) => y * H;

  ctx.fillStyle = "rgba(255,255,255,0.30)";
  for (const p of lm) ctx.fillRect(fx(p.x) - 1, fy(p.y) - 1, 2, 2);

  const traco = (idx: number[], cor: string) => {
    ctx.strokeStyle = cor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    idx.forEach((i, k) => {
      const p = lm[i];
      if (!p) return;
      const x = fx(p.x);
      const y = fy(p.y);
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
  };

  if (hud) {
    traco(OLHO_ESQ, hud.earE > 0.2 ? "#22c55e" : "#ef4444"); // verde=aberto, vermelho=fechado
    traco(OLHO_DIR, hud.earD > 0.2 ? "#22c55e" : "#ef4444");
    traco(BOCA, "#38bdf8");

    const linhas = [
      `passo: ${hud.passo}`,
      `piscadas: ${hud.piscadas}/${PISCADAS_EXIGIDAS}`,
      `EAR E/D: ${hud.earE.toFixed(2)} / ${hud.earD.toFixed(2)}`,
      `sorriso: ${hud.smile.toFixed(2)}  giro: ${hud.yaw.toFixed(2)}`,
    ];
    ctx.font = "12px ui-monospace, monospace";
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(6, 6, 220, 16 * linhas.length + 8);
    ctx.fillStyle = "#e5e7eb";
    linhas.forEach((t, i) => ctx.fillText(t, 12, 24 + i * 16));
  }
}

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
  login,
  modo = "login",
}: {
  onSuccess: (prova: ProvaBiometrica) => void;
  onClose: () => void;
  /** Para ENTRAR com biometria: o desafio fica preso a este e-mail/CPF. */
  login?: string;
  /** "cadastro" = sequência completa; "login" = só piscar 3x. */
  modo?: ModoBiometria;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const [fase, setFase] = useState<Fase>("carregando");
  const [erro, setErro] = useState<string | null>(null);
  const [desafio, setDesafio] = useState<Desafio | null>(null);
  const [temRosto, setTemRosto] = useState(false);
  const [passoIdx, setPassoIdx] = useState(0);
  const [progresso, setProgresso] = useState(0);
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  useEffect(() => {
    let parar = false;
    let stream: MediaStream | null = null;
    let landmarker: import("@mediapipe/tasks-vision").FaceLandmarker | null = null;
    let raf = 0;
    let concluido = false;
    let desafioLocal: Desafio | null = null;
    let passos: PassoDesafio[] = [];

    // acumulador final + estado do passo atual
    const quadrosFinais: string[] = [];
    let bufPasso: string[] = [];
    let idx = 0;
    let ultimaCaptura = 0;
    let feitoEm = 0;
    // máquinas de estado do passo atual
    let piscouEstado: "aberto" | "fechado" = "aberto";
    let piscadas = 0;
    let viuNeutro = false;
    let viuFrontal = false;
    let fortes = 0;

    function bs(cats: { categoryName: string; score: number }[], nome: string): number {
      return cats.find((c) => c.categoryName === nome)?.score ?? 0;
    }

    function resetPasso() {
      bufPasso = [];
      feitoEm = 0;
      piscouEstado = "aberto";
      piscadas = 0;
      viuNeutro = false;
      viuFrontal = false;
      fortes = 0;
    }

    function finalizar() {
      if (concluido || !desafioLocal) return;
      concluido = true;
      setFase("ok");
      setProgresso(1);
      const prova: ProvaBiometrica = {
        desafio_id: desafioLocal.desafio_id,
        quadros: quadrosFinais.slice(0, 40),
      };
      setTimeout(() => {
        if (!parar) onSuccessRef.current(prova);
      }, 600);
    }

    async function iniciar() {
      try {
        const d = await pedirDesafio(login, modo);
        if (parar) return;
        desafioLocal = d;
        passos = d.passos;
        setDesafio(d);

        const vision = await import("@mediapipe/tasks-vision");
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM);
        landmarker = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODELO, delegate: "GPU" },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: true,
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
      const agora = performance.now();
      const r = landmarker.detectForVideo(v, agora);
      const lm = r.faceLandmarks?.[0];
      const cats = r.faceBlendshapes?.[0]?.categories ?? [];
      setTemRosto(Boolean(lm));

      const passo = passos[idx];
      if (lm && passo && !concluido) {
        // captura para o passo atual (sem espelhamento), respeitando o teto
        if (agora - ultimaCaptura >= CADENCIA_MS && bufPasso.length < CAP[passo.id]) {
          bufPasso.push(capturar(v));
          ultimaCaptura = agora;
        }

        const blink = Math.max(bs(cats, "eyeBlinkLeft"), bs(cats, "eyeBlinkRight"));
        const smile = (bs(cats, "mouthSmileLeft") + bs(cats, "mouthSmileRight")) / 2;
        const nariz = lm[1];
        const ladoE = lm[234];
        const ladoD = lm[454];
        let yaw = 0;
        if (nariz && ladoE && ladoD) {
          const meio = (ladoE.x + ladoD.x) / 2;
          yaw = (nariz.x - meio) / (Math.abs(ladoD.x - ladoE.x) || 1);
        }

        let feito = false;
        if (passo.id === "piscar3") {
          if (piscouEstado === "aberto" && blink > BLINK_FECHADO) piscouEstado = "fechado";
          else if (piscouEstado === "fechado" && blink < BLINK_ABERTO) {
            piscouEstado = "aberto";
            piscadas += 1;
          }
          setProgresso(Math.min(1, piscadas / PISCADAS_EXIGIDAS));
          feito = piscadas >= PISCADAS_EXIGIDAS;
        } else if (passo.id === "sorrir") {
          if (smile < SORRISO_NEUTRO) viuNeutro = true;
          setProgresso(Math.min(1, smile / SORRISO_ALVO));
          feito = viuNeutro && smile > SORRISO_ALVO;
        } else {
          if (Math.abs(yaw) < YAW_FRONTAL) viuFrontal = true;
          const virado = passo.id === "virar_esquerda" ? yaw > YAW_GIRO : yaw < -YAW_GIRO;
          if (virado) fortes += 1;
          setProgresso(Math.min(1, fortes / GIRO_QUADROS));
          feito = viuFrontal && fortes >= GIRO_QUADROS;
        }

        if (DEBUG_OVERLAY && overlayRef.current) {
          desenharOverlay(overlayRef.current, v, lm, {
            passo: passo.id,
            piscadas,
            earE: earDe(lm, OLHO_ESQ),
            earD: earDe(lm, OLHO_DIR),
            smile,
            yaw,
          });
        }

        const minQuadros = passo.id === "piscar3" ? 8 : 3;
        if (feito && feitoEm === 0 && bufPasso.length >= minQuadros) feitoEm = agora;
        if (feitoEm > 0 && agora - feitoEm >= POS_MS) {
          quadrosFinais.push(...bufPasso);
          idx += 1;
          setPassoIdx(idx);
          setProgresso(0);
          resetPasso();
          if (idx >= passos.length) {
            finalizar();
            return;
          }
        }
      } else if (DEBUG_OVERLAY && overlayRef.current && v) {
        desenharOverlay(overlayRef.current, v, undefined, null);
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
  }, [login, modo]);

  const passoAtual = desafio?.passos[Math.min(passoIdx, desafio.passos.length - 1)];
  const instrucao = passoAtual?.instrucao ?? "Preparando…";

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
        {DEBUG_OVERLAY && (
          <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
        )}
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
            <p className="text-xl font-semibold">{instrucao}</p>
            <p className="mt-2 text-sm text-ink-foreground/60">
              {temRosto ? "Siga a instrução acima" : "Posicione o rosto dentro do oval"}
            </p>
            {desafio && desafio.passos.length > 1 && (
              <div className="mt-5 flex justify-center gap-2">
                {desafio.passos.map((p, i) => (
                  <span
                    key={p.id}
                    className={`h-1.5 w-8 rounded-full ${
                      i < passoIdx ? "bg-pos" : i === passoIdx ? "bg-marca" : "bg-ink-foreground/20"
                    }`}
                  />
                ))}
              </div>
            )}
            <div className="mx-auto mt-4 h-1.5 w-40 overflow-hidden rounded-full bg-ink-foreground/15">
              <div
                className="h-full rounded-full bg-marca transition-all"
                style={{ width: `${Math.round(progresso * 100)}%` }}
              />
            </div>
          </>
        )}
      </div>

      <p className="mt-auto px-6 pb-8 pt-6 text-center text-xs text-ink-foreground/45">
        Filmamos alguns quadros só para esta verificação. Eles não são guardados: o banco mantém
        apenas um código matemático do seu rosto, criptografado.
      </p>
    </div>
  );
}
