import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ButtonHTMLAttributes,
} from "react";
import { Capacitor, type PluginListenerHandle } from "@capacitor/core";
import { App } from "@capacitor/app";
import { Network } from "@capacitor/network";
import { Keyboard } from "@capacitor/keyboard";
import { StatusBar, Style } from "@capacitor/status-bar";
import { useRouter } from "@tanstack/react-router";
import { get, MODO_API, refreshDaSessao } from "./http";

/** O último fechamento registrado na mesma prioridade vem primeiro. */
export class PilhaVoltar {
  private itens: { fechar: () => void; prioridade: number }[] = [];
  registrar(fechar: () => void, prioridade = 0) {
    const item = { fechar, prioridade };
    this.itens.push(item);
    return () => {
      this.itens = this.itens.filter((i) => i !== item);
    };
  }
  fechar(prioridadeMinima = 0) {
    const item = this.itens.reduce<(typeof this.itens)[number] | undefined>(
      (atual, i) => (!atual || i.prioridade >= atual.prioridade ? i : atual),
      undefined,
    );
    if (!item || item.prioridade < prioridadeMinima) return false;
    this.itens = this.itens.filter((i) => i !== item);
    item.fechar();
    return true;
  }
}
const pilha = new PilhaVoltar();
export function useFecharAoVoltar(aberto: unknown, fechar: () => void, prioridade = 0) {
  const ativo = Boolean(aberto);
  const ref = useRef(fechar);
  ref.current = fechar;
  useEffect(
    () => (ativo ? pilha.registrar(() => ref.current(), prioridade) : undefined),
    [ativo, prioridade],
  );
}

let offline = false;
const ouvintes = new Set<() => void>();
export function atualizarConexao(conectado: boolean) {
  offline = !conectado;
  ouvintes.forEach((fn) => fn());
}
export function useOffline() {
  return useSyncExternalStore(
    (fn) => {
      ouvintes.add(fn);
      return () => {
        ouvintes.delete(fn);
      };
    },
    () => offline,
    () => false,
  );
}
/** Conserva os bloqueios da tela e bloqueia também quando a rede cai. */
export function BotaoFinanceiro({ disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const semRede = useOffline();
  return <button {...props} disabled={disabled || semRede} />;
}

export function criarVoltar({
  fechar,
  inicio,
  voltar,
  avisar,
  sair,
  agora = Date.now,
}: {
  fechar: () => boolean;
  inicio: () => boolean;
  voltar: () => void;
  avisar: () => void;
  sair: () => void;
  agora?: () => number;
}) {
  let ultimo: number | null = null;
  return () => {
    if (fechar()) {
      ultimo = null;
      return;
    }
    if (!inicio()) {
      ultimo = null;
      voltar();
      return;
    }
    const tempo = agora();
    if (ultimo !== null && tempo - ultimo < 2000) {
      ultimo = null;
      sair();
    } else {
      ultimo = tempo;
      avisar();
    }
  };
}

export function AmbienteAndroid() {
  const router = useRouter();
  const semRede = useOffline();
  const [aviso, setAviso] = useState(false);
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    let encerrado = false;
    let revisaoRede = 0;
    const handles: PluginListenerHandle[] = [];
    const revelarCampo = () => {
      const campo = document.activeElement;
      if (campo instanceof HTMLElement && campo.matches("input, textarea, select")) {
        campo.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    };
    document.addEventListener("focusin", revelarCampo);
    const guardar = async (p: Promise<PluginListenerHandle>) => {
      const h = await p;
      if (encerrado) await h.remove();
      else handles.push(h);
    };
    const configurar = async () => {
      const voltar = criarVoltar({
        fechar: () => pilha.fechar(),
        inicio: () => ["/inicio", "/login", "/"].includes(router.state.location.pathname),
        voltar: () => {
          if (router.history.canGoBack()) router.history.back();
          else
            void router.navigate({ to: refreshDaSessao() ? "/inicio" : "/login", replace: true });
        },
        avisar: () => setAviso(true),
        sair: () => {
          void App.exitApp();
        },
      });
      // Uma falha de rede ou aparência não pode desligar o botão Voltar.
      await Promise.allSettled([
        guardar(App.addListener("backButton", voltar)),
        guardar(
          App.addListener("appStateChange", ({ isActive }) => {
            if (!isActive) {
              setAviso(false);
              while (pilha.fechar(50)) {
                /* encerra a câmera */
              }
              return;
            }
            if (MODO_API && refreshDaSessao()) void get("/auth/eu").catch(() => {});
          }),
        ),
        guardar(Keyboard.addListener("keyboardDidShow", revelarCampo)),
        StatusBar.setBackgroundColor({ color: "#0A0A0A" }),
        StatusBar.setStyle({ style: Style.Dark }),
        (async () => {
          await guardar(
            Network.addListener("networkStatusChange", (s) => {
              revisaoRede++;
              atualizarConexao(s.connected);
            }),
          );
          const revisao = revisaoRede;
          const status = await Network.getStatus();
          if (!encerrado && revisao === revisaoRede) atualizarConexao(status.connected);
        })(),
      ]);
    };
    void configurar().catch(() => {});
    return () => {
      encerrado = true;
      document.removeEventListener("focusin", revelarCampo);
      handles.forEach((h) => {
        void h.remove();
      });
    };
  }, [router]);
  useEffect(() => {
    if (!aviso) return;
    const timer = setTimeout(() => setAviso(false), 2000);
    return () => clearTimeout(timer);
  }, [aviso]);
  return (
    <>
      {semRede && (
        <div
          role="status"
          className="sticky top-0 z-[60] bg-tint px-4 py-2 text-center text-sm text-mut2"
          style={{ paddingTop: "max(0.5rem, env(safe-area-inset-top))" }}
        >
          Sem conexão
        </div>
      )}
      {aviso && (
        <div
          role="status"
          className="fixed bottom-24 left-1/2 z-[60] -translate-x-1/2 whitespace-nowrap rounded-full bg-ink px-4 py-3 text-sm text-ink-foreground"
        >
          Toque de novo para sair
        </div>
      )}
    </>
  );
}
