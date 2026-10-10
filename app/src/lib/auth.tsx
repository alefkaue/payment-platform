import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { sair as sairApi, selecionarConta } from "./api";
import { aoExpirarSessao } from "./http";
import type { Conta, LoginResposta, Pessoa } from "./types";

/**
 * Sessão do app. O login é da PESSOA; ela pode operar várias contas (a pessoal
 * e as das empresas em que tem vínculo). `conta` é a que está em uso — o
 * seletor no cabeçalho troca entre elas (no backend, header X-Conta).
 */
interface AuthState {
  ready: boolean;
  conta: Conta | null;
  contas: Conta[];
  /** A pessoa logada (nome, e-mail, CPF). */
  pessoa: Pessoa | null;
  entrar: (r: LoginResposta) => void;
  trocarConta: (c: Conta) => void;
  sair: () => void;
}

const Ctx = createContext<AuthState | null>(null);
const KEY = "payflow-session";

interface Salvo {
  conta: Conta;
  contas: Conta[];
  pessoa?: Pessoa | null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [conta, setConta] = useState<Conta | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [pessoa, setPessoa] = useState<Pessoa | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) {
        const s = JSON.parse(raw) as Partial<Salvo>;
        if (s.conta) {
          setConta(s.conta);
          setContas(s.contas ?? [s.conta]);
          setPessoa(s.pessoa ?? null);
          selecionarConta(s.conta);
        }
      }
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  // O servidor encerrou a sessão (tempo máximo, inatividade, encerrada em outro
  // aparelho...): limpa o estado e o layout do app manda para o login, que mostra
  // o motivo (motivoSaida). Não chama /auth/logout: a sessão já não existe.
  useEffect(
    () =>
      aoExpirarSessao(() => {
        setConta(null);
        setContas([]);
        setPessoa(null);
        qc.clear(); // nada da sessão anterior fica na tela
        try {
          sessionStorage.removeItem(KEY);
        } catch {
          /* ignore */
        }
      }),
    [qc],
  );

  function salvar(c: Conta | null, cs: Conta[], p: Pessoa | null) {
    setConta(c);
    setContas(cs);
    setPessoa(p);
    try {
      if (c)
        sessionStorage.setItem(
          KEY,
          JSON.stringify({ conta: c, contas: cs, pessoa: p } satisfies Salvo),
        );
      else sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }

  const entrar = (r: LoginResposta) => {
    selecionarConta(r.conta);
    salvar(r.conta, r.contas, r.pessoa ?? null);
  };
  const trocarConta = (c: Conta) => {
    selecionarConta(c);
    salvar(c, contas, pessoa);
  };
  const sair = () => {
    void sairApi();
    salvar(null, [], null);
  };

  return (
    <Ctx.Provider value={{ ready, conta, contas, pessoa, entrar, trocarConta, sair }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
