import React, { createContext, useCallback, useEffect, useState } from "react";
import { api, temSessao } from "./api";

export const AuthContext = createContext({ logado: false, entrar: async () => {}, sair: async () => {} });

export function AuthProvider({ children }) {
  const [logado, setLogado] = useState(false);
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    (async () => {
      setLogado(await temSessao());
      setPronto(true);
    })();
  }, []);

  const entrar = useCallback(async () => setLogado(true), []);
  const sair = useCallback(async () => {
    await api.logout();
    setLogado(false);
  }, []);

  if (!pronto) return null;
  return <AuthContext.Provider value={{ logado, entrar, sair }}>{children}</AuthContext.Provider>;
}
