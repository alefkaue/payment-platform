import { useEffect, useRef, useState } from "react";
import { useFecharAoVoltar } from "@/lib/mobile";
import { Check, Loader2, X } from "lucide-react";
import { pedirDesafio } from "@/lib/api";
import { ContadorPiscadas } from "@/lib/piscadas";
import {
  giroDoRosto,
  mediana,
  medirRosto,
  orientarRosto,
  PREPARO_MS,
  YAW_OCULOS,
} from "@/lib/qualidade-rosto";
import {
  CADENCIA_MS,
  cotaPorPasso,
  MAX_QUADROS,
  selecionarQuadros,
  TEMPO_PASSO_MS,
  type Quadro,
} from "@/lib/captura-facial";
import type {
  Desafio,
  ModoBiometria,
  PassoBiometria,
  PassoDesafio,
  ProvaBiometrica,
} from "@/lib/types";

/**
 * Verificação facial com prova de vida, guiada por um DESAFIO DO SERVIDOR em
 * VÁRIOS PASSOS. O servidor SORTEIA as ações e a ordem a cada vez (anti-replay:
 * uma gravação antiga não serve para o desafio novo):
 *
 * - modo "cadastro": piscar (2 ou 3x), sorrir e virar para os 2 lados, em ordem sorteada.
 * - modo "login": 2 dessas ações. É o 2º fator do login: o desafio vem pronto
 *   da etapa da senha (POST /auth/login) e é passado em `desafio`.
 *
 * Como funciona:
 * 1. PREPARO: só começa com a captura boa (um rosto, distância, centro, luz e, no
 *    cadastro, sem óculos -- medidos com o rosto de frente).
 * 2. PASSOS: a câmera grava em RAJADA (~10 quadros por segundo, como um vídeo). O passo
 *    acaba quando o app vê o movimento ou quando o tempo do passo acaba; nada trava a
 *    pessoa no meio. No fim de cada passo guardamos os quadros que mostram a ação.
 * 3. No fim mandamos as imagens salvas. QUEM DECIDE é o servidor: ele reextrai os
 *    landmarks, confere a sequência inteira, a luz e os óculos nos quadros frontais, faz
 *    anti-spoofing e compara o rosto.
 *
 * No webview do apk (Capacitor) exige a permissão CAMERA no AndroidManifest.
 */

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODELO =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Limiares do GUIA (blendshapes 0..1 e giro). Só servem para o passo acabar assim que o
// movimento aparece, com folga sobre os do servidor; sem eles, o passo acaba pelo tempo.
// Piscar usa limiares calibrados pela pessoa (lib/piscadas).
const SORRISO_NEUTRO = 0.15;
const SORRISO_ALVO = 0.5;
const YAW_FRONTAL = 0.06;
const YAW_GIRO = 0.26;
const GIRO_QUADROS = 3;
const piscadasDo = (id: PassoBiometria) => (id === "piscar2" ? 2 : 3);
// Depois de ver o movimento, grava mais um instante (o "depois" da ação).
const POS_MS = 600;
// Pausa entre passos: tempo para a pessoa ler a instrução E resetar a expressão.
// Sem pausa suficiente, expressões do passo anterior "vazam" para o próximo.
const ENTRE_PASSOS_MS = 1500;
// Medição de luz/distância/óculos no preparo: a cada 120 ms; óculos pela mediana.
const QUALIDADE_MS = 120;
const OCULOS_JANELA = 7;
// Sem rosto por mais que isso no meio de um passo: o passo recomeça do zero.
const SEM_ROSTO_MAX_MS = 1200;
// O desafio do servidor vale 120 s: antes disso a tela encerra e oferece "Tentar de novo"
// (que pede um desafio novo), em vez de mandar uma prova que já nasceria vencida.
const PRAZO_TOTAL_MS = 105_000;

// DEV: desenha onde o rosto é detectado (malha + olhos abrindo/fechando + boca +
// métricas ao vivo). Só no `npm run dev` -- nunca no build de produção (não dá
// pistas a quem tenta burlar a prova de vida).
const DEBUG_OVERLAY = import.meta.env.DEV;
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
  blink: number;
  guardados: number;
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
      `piscadas: ${hud.piscadas}  olho fechado: ${hud.blink.toFixed(2)}`,
      `quadros guardados: ${hud.guardados}`,
      `EAR E/D: ${hud.earE.toFixed(2)} / ${hud.earD.toFixed(2)}`,
      `sorriso: ${hud.smile.toFixed(2)}  giro: ${hud.yaw.toFixed(2)}`,
    ];
    ctx.font = "12px ui-monospace, monospace";
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(6, 6, 260, 16 * linhas.length + 8);
    ctx.fillStyle = "#e5e7eb";
    linhas.forEach((t, i) => ctx.fillText(t, 12, 24 + i * 16));
  }
}

type Fase = "carregando" | "preparo" | "ativo" | "ok" | "erro";

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
  desafio: desafioPronto,
  modo = "login",
  erroServidor,
  onRetry,
}: {
  onSuccess: (prova: ProvaBiometrica) => void | Promise<unknown>;
  onClose: () => void;
  /** Desafio já emitido pelo servidor (o do login vem junto com o mfa_token). */
  desafio?: Desafio;
  /** "cadastro" = sequência completa; "login" = 2 ações. */
  modo?: ModoBiometria;
  erroServidor?: string | null;
  onRetry?: () => void | Promise<void>;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  useFecharAoVoltar(true, onClose, 50);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const [fase, setFase] = useState<Fase>("carregando");
  const [erro, setErro] = useState<string | null>(null);
  const [desafio, setDesafio] = useState<Desafio | null>(null);
  const [temRosto, setTemRosto] = useState(false);
  const [qualidadeBoa, setQualidadeBoa] = useState(false);
  const [orientacao, setOrientacao] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [reiniciando, setReiniciando] = useState(false);
  const [passoIdx, setPassoIdx] = useState(0);
  const [progresso, setProgresso] = useState(0);
  // Proporção real da câmera (largura/altura): a moldura segue a câmera, sem zoom nem
  // esticar a imagem (webcam de PC é deitada; câmera de celular em pé).
  const [proporcao, setProporcao] = useState(3 / 4);
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  useEffect(() => {
    setFase("carregando");
    setPassoIdx(0);
    setProgresso(0);
    setOrientacao(null);
    let parar = false;
    let stream: MediaStream | null = null;
    let landmarker: import("@mediapipe/tasks-vision").FaceLandmarker | null = null;
    let raf = 0;
    let concluido = false;
    let desafioLocal: Desafio | null = null;
    let passos: PassoDesafio[] = [];
    let preparado = false;
    let bomDesde: number | null = null;
    let ultimaQualidade = Number.NEGATIVE_INFINITY;
    let avisoPreparo: string | null = "Posicione o rosto no círculo";
    const oculosFrontais: number[] = [];
    const qualidadeCanvas = document.createElement("canvas");
    qualidadeCanvas.width = 320;
    const qualidadeCtx = qualidadeCanvas.getContext("2d", { willReadFrequently: true });

    // acumulador final + estado do passo atual
    const quadrosFinais: string[] = [];
    let rajada: Quadro[] = [];
    let idx = 0;
    let inicioPasso = 0;
    let ultimaCaptura = 0;
    let feitoEm = 0;
    let semRostoDesde: number | null = null;
    let desafioEm = 0;
    // máquinas de estado do passo atual (só para saber quando o movimento aconteceu)
    const contador = new ContadorPiscadas();
    let piscadas = 0;
    let viuNeutro = false;
    let sorrisoGravado = false;
    let viuFrontal = false;
    let fortes = 0;

    function bs(cats: { categoryName: string; score: number }[], nome: string): number {
      return cats.find((c) => c.categoryName === nome)?.score ?? 0;
    }

    function comecarPasso(agora: number) {
      rajada = [];
      inicioPasso = agora;
      feitoEm = 0;
      semRostoDesde = null;
      ultimaCaptura = 0;
      contador.recomecar();
      piscadas = 0;
      viuNeutro = false;
      sorrisoGravado = false;
      viuFrontal = false;
      fortes = 0;
    }

    function encerrarPasso(passo: PassoDesafio, agora: number) {
      const cota = Math.min(cotaPorPasso(passos.length), MAX_QUADROS - quadrosFinais.length);
      quadrosFinais.push(...selecionarQuadros(rajada, passo.id, cota).map((q) => q.img));
      idx += 1;
      setPassoIdx(idx);
      setProgresso(0);
      if (idx >= passos.length) {
        finalizar();
        return;
      }
      // Pequena pausa para ler a próxima instrução antes de gravar o passo seguinte.
      comecarPasso(agora + ENTRE_PASSOS_MS);
    }

    function finalizar() {
      if (concluido || !desafioLocal) return;
      concluido = true;
      setFase("ok");
      setProgresso(1);
      const prova: ProvaBiometrica = {
        desafio_id: desafioLocal.desafio_id,
        quadros: quadrosFinais.slice(0, MAX_QUADROS),
      };
      setTimeout(() => {
        if (!parar) {
          Promise.resolve()
            .then(() => onSuccessRef.current(prova))
            .catch((e: unknown) => {
              if (parar) return;
              setErro(
                e instanceof Error
                  ? e.message
                  : "Não foi possível conferir o rosto. Tente de novo.",
              );
              setFase("erro");
            });
        }
      }, 600);
    }

    async function iniciar() {
      try {
        const vision = await import("@mediapipe/tasks-vision");
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM);
        if (parar) return;
        const criar = (delegate: "GPU" | "CPU") =>
          vision.FaceLandmarker.createFromOptions(fileset, {
            baseOptions: { modelAssetPath: MODELO, delegate },
            runningMode: "VIDEO",
            numFaces: 2,
            outputFaceBlendshapes: true,
          });
        // Aparelho/navegador sem WebGL utilizável: cai para CPU em vez de falhar.
        landmarker = await criar("GPU").catch(() => criar("CPU"));
        if (parar) {
          landmarker.close();
          return;
        }
        // Sem forçar largura/altura exatas: o navegador recortava/esticava para caber.
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
        if (parar) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const v = videoRef.current;
        if (!v) return;
        v.srcObject = stream;
        await v.play();
        if (parar) return;
        if (v.videoWidth && v.videoHeight) setProporcao(v.videoWidth / v.videoHeight);
        // O desafio só é pedido com modelo e câmera prontos: o prazo dele (120 s) não
        // corre durante o download do modelo nem enquanto a pessoa permite a câmera.
        const d = desafioPronto ?? (await pedirDesafio(modo));
        if (parar) return;
        desafioLocal = d;
        passos = d.passos;
        desafioEm = performance.now();
        setDesafio(d);
        setFase("preparo");
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

    /** Preparo: luz, distância, centro e (cadastro) óculos. Só libera com tudo bom. */
    function preparar(v: HTMLVideoElement, lm: Pt[] | undefined, rostos: number, agora: number) {
      if (agora - ultimaQualidade >= QUALIDADE_MS) {
        ultimaQualidade = agora;
        qualidadeCanvas.height = Math.max(1, Math.round((320 * v.videoHeight) / v.videoWidth));
        qualidadeCtx?.drawImage(v, 0, 0, qualidadeCanvas.width, qualidadeCanvas.height);
        const pixels = qualidadeCtx?.getImageData(
          0,
          0,
          qualidadeCanvas.width,
          qualidadeCanvas.height,
        );
        if (!pixels) {
          avisoPreparo = "Não foi possível avaliar a câmera";
        } else {
          const m = medirRosto(
            pixels.data,
            qualidadeCanvas.width,
            qualidadeCanvas.height,
            lm ?? [],
            rostos,
          );
          // Óculos só com o rosto de frente, pela mediana dos últimos quadros: um quadro
          // ruim (rosto virando, desfoque) não acusa óculos sozinho.
          if (lm && Math.abs(giroDoRosto(lm)) < YAW_OCULOS) {
            oculosFrontais.push(m.oculos);
            if (oculosFrontais.length > OCULOS_JANELA) oculosFrontais.shift();
          }
          m.oculos = oculosFrontais.length >= 3 ? mediana(oculosFrontais) : 0;
          avisoPreparo = orientarRosto(m, modo === "cadastro");
        }
      }
      setOrientacao(avisoPreparo);
      setQualidadeBoa(!avisoPreparo);
      if (avisoPreparo) {
        bomDesde = null;
        return;
      }
      bomDesde ??= agora;
      if (agora - bomDesde < PREPARO_MS) {
        setOrientacao("Ótimo! Mantenha o rosto assim");
        return;
      }
      preparado = true;
      setOrientacao(null);
      setFase("ativo");
      comecarPasso(agora);
    }

    function loop() {
      const v = videoRef.current;
      if (parar) return;
      if (!landmarker || !v || v.readyState < 2) {
        raf = requestAnimationFrame(loop);
        return;
      }
      const agora = performance.now();
      if (desafioEm && agora - desafioEm > PRAZO_TOTAL_MS && !concluido) {
        concluido = true;
        setErro("O tempo da verificação acabou. Toque em Tentar de novo.");
        setFase("erro");
        return;
      }
      const r = landmarker.detectForVideo(v, agora);
      const rostos = r.faceLandmarks?.length ?? 0;
      const lm = r.faceLandmarks?.[0];
      const cats = r.faceBlendshapes?.[0]?.categories ?? [];
      setTemRosto(Boolean(lm));

      if (!preparado) {
        // Calibra o olho aberto da pessoa já no preparo (sem contar piscadas).
        if (lm && rostos === 1) {
          const b = Math.max(bs(cats, "eyeBlinkLeft"), bs(cats, "eyeBlinkRight"));
          contador.observar(b, giroDoRosto(lm), false);
        }
        preparar(v, lm, rostos, agora);
        raf = requestAnimationFrame(loop);
        return;
      }

      const passo = passos[idx];
      if (!passo || concluido) return;
      if (agora < inicioPasso) {
        // pausa entre passos: mostra a próxima instrução, ainda sem gravar
        raf = requestAnimationFrame(loop);
        return;
      }
      // Sem rosto (ou com dois) não grava o quadro. Uma falha curta (piscar de detecção) não
      // atrapalha; ausência longa recomeça SÓ este passo: o servidor tem de ver a ação
      // inteira de forma contínua, não pedaços com buracos.
      if (!lm || rostos !== 1) {
        semRostoDesde ??= agora;
        if (agora - semRostoDesde >= SEM_ROSTO_MAX_MS) {
          comecarPasso(agora);
          setProgresso(0);
        }
        setOrientacao(rostos > 1 ? "Fique sozinho na câmera" : "Volte o rosto para a câmera");
        raf = requestAnimationFrame(loop);
        return;
      }
      semRostoDesde = null;
      setOrientacao(null);

      const blink = Math.max(bs(cats, "eyeBlinkLeft"), bs(cats, "eyeBlinkRight"));
      const smile = (bs(cats, "mouthSmileLeft") + bs(cats, "mouthSmileRight")) / 2;
      const yaw = giroDoRosto(lm);

      // Rajada: um quadro a cada CADENCIA_MS, sempre (como um vídeo). Piscada é rápida
      // (~150 ms): com o olho fechando, grava no ritmo da câmera para não perder.
      const ehPiscar = passo.id === "piscar2" || passo.id === "piscar3";
      piscadas = contador.observar(blink, yaw, ehPiscar);
      const olhoFechando = contador.fechando(blink) && agora - ultimaCaptura >= 30;
      let gravou = false;
      if (agora - ultimaCaptura >= CADENCIA_MS || olhoFechando) {
        rajada.push({ img: capturar(v), t: agora, blink, smile, yaw });
        ultimaCaptura = agora;
        gravou = true;
      }

      // Só para saber quando o movimento já aconteceu (e mostrar o progresso).
      let feito = false;
      if (ehPiscar) {
        const exigidas = piscadasDo(passo.id);
        setProgresso(Math.min(1, piscadas / exigidas));
        feito = piscadas >= exigidas;
      } else if (passo.id === "sorrir") {
        // Sorriso e giro só contam nos quadros GRAVADOS: o servidor só vê esses.
        if (gravou && smile < SORRISO_NEUTRO) viuNeutro = true;
        if (gravou && viuNeutro && smile > SORRISO_ALVO) sorrisoGravado = true;
        setProgresso(Math.min(1, smile / SORRISO_ALVO));
        feito = sorrisoGravado;
      } else {
        if (gravou && Math.abs(yaw) < YAW_FRONTAL) viuFrontal = true;
        const virado = passo.id === "virar_esquerda" ? yaw > YAW_GIRO : yaw < -YAW_GIRO;
        if (gravou && virado && viuFrontal) fortes += 1;
        setProgresso(Math.min(1, fortes / GIRO_QUADROS));
        feito = viuFrontal && fortes >= GIRO_QUADROS;
      }

      if (DEBUG_OVERLAY && overlayRef.current) {
        desenharOverlay(overlayRef.current, v, lm, {
          passo: passo.id,
          piscadas,
          blink,
          guardados: quadrosFinais.length + rajada.length,
          earE: earDe(lm, OLHO_ESQ),
          earD: earDe(lm, OLHO_DIR),
          smile,
          yaw,
        });
      }

      if (feito && feitoEm === 0) feitoEm = agora;
      const acabouTempo = agora - inicioPasso >= TEMPO_PASSO_MS[passo.id];
      if ((feitoEm > 0 && agora - feitoEm >= POS_MS) || acabouTempo) {
        encerrarPasso(passo, agora);
        if (concluido) return;
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
    // Recomeça só quando muda o desafio (nova tentativa) ou o modo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desafioPronto?.desafio_id, modo, tentativa]);

  const passoAtual = desafio?.passos[Math.min(passoIdx, desafio.passos.length - 1)];
  const instrucao =
    orientacao ??
    (fase === "preparo"
      ? "Posicione o rosto no círculo"
      : (passoAtual?.instrucao ?? "Preparando…"));
  const falha = (fase === "erro" ? erro : null) || erroServidor;

  async function tentarNovamente() {
    setReiniciando(true);
    try {
      if (erroServidor && onRetry) await onRetry();
      else {
        setErro(null);
        setFase("carregando");
        setTentativa((n) => n + 1);
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível recomeçar. Tente de novo.");
      setFase("erro");
    } finally {
      setReiniciando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink text-ink-foreground">
      <div
        style={{ paddingTop: "calc(1.5rem + env(safe-area-inset-top))" }}
        className="flex items-center justify-between px-5"
      >
        <p className="font-semibold">Verificação facial</p>
        <button aria-label="Fechar" onClick={onClose} className="text-ink-foreground/70">
          <X size={22} />
        </button>
      </div>

      <div
        style={{ aspectRatio: String(proporcao) }}
        className={`relative mx-auto mt-4 overflow-hidden rounded-[28px] bg-black ring-1 ring-ink-foreground/10 ${
          proporcao > 1 ? "w-[min(92%,420px)]" : "w-[min(86%,340px)]"
        }`}
      >
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
          className={`pointer-events-none absolute left-1/2 top-[7%] aspect-[3/4] h-[86%] -translate-x-1/2 rounded-[50%] border-2 transition-colors ${
            falha ? "border-errt" : fase === "ok" || fase === "ativo" || qualidadeBoa ? "border-pos" : "border-pending"
          }`}
        />
        {fase === "carregando" && (
          <div className="absolute inset-0 grid place-items-center bg-black/40 text-sm">
            <span className="flex items-center gap-2">
              <Loader2 className="animate-spin" size={18} /> Preparando a câmera…
            </span>
          </div>
        )}
        {fase === "ok" && !falha && (
          <div className="absolute inset-0 grid place-items-center bg-black/50">
            <span className="grid h-16 w-16 place-items-center rounded-full bg-pos text-ink-foreground">
              <Check size={32} strokeWidth={3} />
            </span>
          </div>
        )}
      </div>

      <div className="mt-7 px-6 text-center">
        {falha ? (
          <>
            <p aria-live="assertive" className="text-xl font-semibold">
              {falha}
            </p>
            <button
              disabled={reiniciando}
              onClick={() => void tentarNovamente()}
              className="btn btn-glass mt-5 w-full"
            >
              {reiniciando ? "Preparando…" : "Tentar de novo"}
            </button>
          </>
        ) : fase === "ok" ? (
          <p className="text-lg font-semibold text-pos">Pronto! Conferindo com o banco…</p>
        ) : (
          <>
            <p aria-live="polite" aria-atomic="true" className="text-2xl font-semibold">
              {instrucao}
            </p>
            <p className="mt-2 text-sm text-ink-foreground/60">
              {temRosto ? "Siga a instrução acima" : "Posicione o rosto dentro do oval"}
            </p>
            {desafio && desafio.passos.length > 1 && (
              <div className="mt-5 flex justify-center gap-2">
                {desafio.passos.map((p, i) => (
                  <span
                    key={p.id}
                    className={`h-1.5 w-8 rounded-full ${
                      i < passoIdx
                        ? "bg-pos"
                        : i === passoIdx
                          ? "bg-pending"
                          : "bg-ink-foreground/20"
                    }`}
                  />
                ))}
              </div>
            )}
            <div
              role="progressbar"
              aria-label="Progresso dos passos"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(
                ((passoIdx + progresso) / (desafio?.passos.length || 1)) * 100,
              )}
              className="mx-auto mt-4 h-1.5 w-40 overflow-hidden rounded-full bg-ink-foreground/15"
            >
              <div
                className="h-full rounded-full bg-pos transition-all"
                style={{
                  width: `${Math.round(((passoIdx + progresso) / (desafio?.passos.length || 1)) * 100)}%`,
                }}
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
