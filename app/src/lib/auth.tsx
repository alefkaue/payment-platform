import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { sair as sairApi, selecionarConta } from "./api";
import type { Conta, LoginResposta } from "./types";

/**
 * Sessão do app. O login é da PESSOA; ela pode operar várias contas (a pessoal
 * e as das empresas em que tem vínculo). `conta` é a que está em uso — o
 * seletor no cabeçalho troca entre elas (no backend, header X-Conta).
 */
interface AuthState {
  ready: boolean;
  conta: Conta | null;
  contas: Conta[];
  entrar: (r: LoginResposta) => void;
  trocarConta: (c: Conta) => void;
  sair: () => void;
}

const Ctx = createContext<AuthState | null>(null);
const KEY = "payflow-session";

interface Salvo {
  conta: Conta;
  contas: Conta[];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [conta, setConta] = useState<Conta | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) {
        const s = JSON.parse(raw) as Partial<Salvo>;
        if (s.conta) {
          setConta(s.conta);
          setContas(s.contas ?? [s.conta]);
          selecionarConta(s.conta);
        }
      }
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  function salvar(c: Conta | null, cs: Conta[]) {
    setConta(c);
    setContas(cs);
    try {
      if (c) sessionStorage.setItem(KEY, JSON.stringify({ conta: c, contas: cs } satisfies Salvo));
      else sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }

  const entrar = (r: LoginResposta) => {
    selecionarConta(r.conta);
    salvar(r.conta, r.contas);
  };
  const trocarConta = (c: Conta) => {
    selecionarConta(c);
    salvar(c, contas);
  };
  const sair = () => {
    void sairApi();
    salvar(null, []);
  };

  return (
    <Ctx.Provider value={{ ready, conta, contas, entrar, trocarConta, sair }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
