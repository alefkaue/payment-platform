// Cliente de API do PayFlow. Guarda access/refresh token no AsyncStorage, injeta
// o Bearer e, em 401, tenta renovar com o refresh token UMA vez antes de desistir
// (fluxo de refresh do backend: /auth/refresh rotaciona o token).

import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";

const API_URL =
  Constants.expoConfig?.extra?.apiUrl ||
  Constants.manifest?.extra?.apiUrl ||
  "http://192.168.0.10:8000";

const CHAVE_ACCESS = "payflow.access";
const CHAVE_REFRESH = "payflow.refresh";

export async function salvarTokens(access, refresh) {
  await AsyncStorage.multiSet([
    [CHAVE_ACCESS, access || ""],
    [CHAVE_REFRESH, refresh || ""],
  ]);
}

export async function limparTokens() {
  await AsyncStorage.multiRemove([CHAVE_ACCESS, CHAVE_REFRESH]);
}

export async function temSessao() {
  return !!(await AsyncStorage.getItem(CHAVE_ACCESS));
}

async function _renovar() {
  const refresh = await AsyncStorage.getItem(CHAVE_REFRESH);
  if (!refresh) return false;
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) {
    await limparTokens();
    return false;
  }
  const tk = await res.json();
  await salvarTokens(tk.access_token, tk.refresh_token);
  return true;
}

async function _request(metodo, caminho, corpo, tentarRenovar = true) {
  const access = await AsyncStorage.getItem(CHAVE_ACCESS);
  const headers = { "Content-Type": "application/json" };
  if (access) headers.Authorization = `Bearer ${access}`;

  let res;
  try {
    res = await fetch(`${API_URL}${caminho}`, {
      method: metodo,
      headers,
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
  } catch (e) {
    throw new Error(
      `Não foi possível conectar ao servidor (${API_URL}). Confirme o IP em app.json e que a API está no ar.`
    );
  }

  if (res.status === 401 && tentarRenovar && access) {
    if (await _renovar()) return _request(metodo, caminho, corpo, false);
  }

  const texto = await res.text();
  const dados = texto ? JSON.parse(texto) : null;
  if (!res.ok) {
    const msg = dados?.detail;
    throw new Error(typeof msg === "string" ? msg : "Erro na requisição.");
  }
  return dados;
}

export const api = {
  url: API_URL,
  // auth
  async login(email, senha) {
    const tk = await _request("POST", "/auth/login", { email, senha });
    await salvarTokens(tk.access_token, tk.refresh_token);
    return tk;
  },
  async logout() {
    const refresh = await AsyncStorage.getItem(CHAVE_REFRESH);
    if (refresh) {
      try {
        await _request("POST", "/auth/logout", { refresh_token: refresh }, false);
      } catch (_) {}
    }
    await limparTokens();
  },
  registrar: (dados) => _request("POST", "/usuarios", dados),
  // contas
  minhaConta: () => _request("GET", "/usuarios/eu"),
  consultarCarteira: (id) => _request("GET", `/usuarios/${id}`),
  // pagamentos
  transferir: (dados) => _request("POST", "/pagamentos/transferir", dados),
  transacoes: () => _request("GET", "/pagamentos/transacoes"),
  simularSplit: (valor, tipoDestino) =>
    _request("GET", `/pagamentos/split/simular?valor=${valor}&tipo_destino=${tipoDestino}`),
  // admin / governo
  depositar: (carteira_id, valor) => _request("POST", "/admin/depositar", { carteira_id, valor }),
  retencoesGoverno: () => _request("GET", "/admin/governo/retencoes"),
};
