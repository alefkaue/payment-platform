import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LivenessCheck } from "@/components/payflow/liveness";

const camera = vi.hoisted(() => ({
  rostos: 1,
  brilho: 120,
  blink: 0,
  stop: vi.fn(),
  close: vi.fn(),
  detectar: vi.fn(),
}));
vi.mock("@/lib/mobile", () => ({ useFecharAoVoltar: vi.fn() }));
vi.mock("@/lib/api", () => ({
  pedirDesafio: vi.fn(async () => ({
    desafio_id: "novo",
    passos: [{ id: "piscar2", instrucao: "Pisque duas vezes" }],
  })),
}));
vi.mock("@mediapipe/tasks-vision", () => ({
  FilesetResolver: { forVisionTasks: vi.fn(async () => ({})) },
  FaceLandmarker: {
    createFromOptions: vi.fn(async () => ({
      close: camera.close,
      detectForVideo: () => {
        camera.detectar();
        return {
          faceLandmarks: Array.from({ length: camera.rostos }, () => [
            { x: 0.25, y: 0.2 },
            { x: 0.75, y: 0.8 },
          ]),
          faceBlendshapes: [
            { categories: [{ categoryName: "eyeBlinkLeft", score: camera.blink }] },
          ],
        };
      },
    })),
  },
}));
let quadro: FrameRequestCallback | undefined;
beforeEach(() => {
  camera.rostos = 1;
  camera.brilho = 120;
  camera.blink = 0;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    quadro = cb;
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: camera.stop }] })) },
  });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(4);
  vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(480);
  vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(640);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        drawImage: vi.fn(),
        clearRect: vi.fn(),
        fillRect: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        closePath: vi.fn(),
        stroke: vi.fn(),
        fillText: vi.fn(),
        getImageData: (_x: number, _y: number, w: number, h: number) => ({
          data: new Uint8ClampedArray(w * h * 4).fill(camera.brilho),
        }),
      }) as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue(
    "data:image/jpeg;base64,quadro",
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  quadro = undefined;
});
async function avancar(tempo: number) {
  vi.spyOn(performance, "now").mockReturnValue(tempo);
  await act(async () => {
    quadro?.(tempo);
  });
}
it("só começa após um segundo bom seguido e pausa sem capturar no escuro", async () => {
  vi.spyOn(performance, "now").mockReturnValue(0);
  const captura = vi.mocked(HTMLCanvasElement.prototype.toDataURL);
  render(<LivenessCheck onSuccess={vi.fn()} onClose={vi.fn()} />);
  await waitFor(() =>
    expect(screen.getByText("Ótimo! Mantenha o rosto assim")).toBeInTheDocument(),
  );
  await avancar(900);
  expect(captura).not.toHaveBeenCalled();
  camera.rostos = 0;
  await avancar(950);
  expect(screen.getByText("Posicione o rosto no círculo")).toBeInTheDocument();
  camera.rostos = 1;
  await avancar(1000);
  await avancar(1999);
  expect(captura).not.toHaveBeenCalled();
  await avancar(2000);
  expect(screen.getByText("Pisque duas vezes")).toBeInTheDocument();
  expect(captura).toHaveBeenCalled();
  const antes = captura.mock.calls.length;
  camera.brilho = 20;
  camera.blink = 1;
  await avancar(2100);
  expect(screen.getByText(/Está escuro/)).toHaveAttribute("aria-live", "polite");
  expect(captura.mock.calls.length).toBe(antes);
  camera.brilho = 120;
  await avancar(2200);
  await avancar(3200);
  expect(screen.getByText("Pisque duas vezes")).toBeInTheDocument();
});
it("mostra a recusa do servidor e solicita novo desafio ao tentar de novo", async () => {
  const repetir = vi.fn();
  render(
    <LivenessCheck
      erroServidor="O rosto mudou durante a verificação."
      onRetry={repetir}
      onSuccess={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByText("O rosto mudou durante a verificação.")).toHaveAttribute(
    "aria-live",
    "assertive",
  );
  fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  await waitFor(() => expect(repetir).toHaveBeenCalledOnce());
});

it("aguarda a resposta assíncrona e recomeça no preparo após a recusa", async () => {
  vi.spyOn(performance, "now").mockReturnValue(0);
  const enviar = vi.fn(async () => {
    throw new Error("Há mais de um rosto na imagem.");
  });
  render(<LivenessCheck onSuccess={enviar} onClose={vi.fn()} />);
  await waitFor(() =>
    expect(screen.getByText("Ótimo! Mantenha o rosto assim")).toBeInTheDocument(),
  );
  vi.useFakeTimers();
  await avancar(1000);
  camera.blink = 1;
  await avancar(1010);
  await avancar(1020);
  camera.blink = 0;
  await avancar(1030);
  camera.blink = 1;
  await avancar(1040);
  await avancar(1050);
  camera.blink = 0;
  await avancar(1060);
  await avancar(1400);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(600);
  });
  expect(enviar).toHaveBeenCalledOnce();
  expect(screen.getByText("Há mais de um rosto na imagem.")).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  });
  expect(screen.getByText("Ótimo! Mantenha o rosto assim")).toBeInTheDocument();
  expect(enviar).toHaveBeenCalledOnce();
});
