import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Conta } from "./types";

interface AuthState {
  ready: boolean;
  conta: Conta | null;
  entrar: (conta: Conta) => void;
  sair: () => void;
}

const Ctx = createContext<AuthState | null>(null);
const KEY = "payflow-session";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [conta, setConta] = useState<Conta | null>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) setConta(JSON.parse(raw).conta);
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  const entrar = (c: Conta) => {
    setConta(c);
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ conta: c }));
    } catch {
      /* ignore */
    }
  };
  const sair = () => {
    setConta(null);
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  };

  return <Ctx.Provider value={{ ready, conta, entrar, sair }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
