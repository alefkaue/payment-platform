import React, { useContext, useState, useCallback } from "react";
import { ScrollView, Text, View, StyleSheet, RefreshControl, Pressable } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { Botao, Campo, Aviso, Card, SplitBar, LinhaValor, SelfieButton } from "../components";
import { AuthContext } from "../auth";
import { api } from "../api";
import { cores, fonte, raio, sombraCard, moeda } from "../theme";

const LIMITE_FACIAL = 500; // espelha LIMITE_FACIAL_REAIS do backend

function parseValor(txt) {
  const n = parseFloat(String(txt).replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? NaN : Math.round(n * 100) / 100;
}

export function InicioScreen({ navigation }) {
  const { sair } = useContext(AuthContext);
  const [conta, setConta] = useState(null);
  const [transacoes, setTransacoes] = useState([]);
  const [erro, setErro] = useState("");
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const [c, t] = await Promise.all([api.minhaConta(), api.transacoes()]);
      setConta(c);
      setTransacoes(t.slice(0, 5));
    } catch (e) {
      setErro(e.message);
    }
  }, []);

  useFocusEffect(useCallback(() => { carregar(); }, [carregar]));

  return (
    <ScrollView
      style={{ backgroundColor: cores.bg }}
      contentContainerStyle={{ padding: 22, paddingTop: 40 }}
      refreshControl={<RefreshControl refreshing={atualizando} onRefresh={async () => { setAtualizando(true); await carregar(); setAtualizando(false); }} />}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ fontSize: fonte.corpo, color: cores.mut2 }}>{conta?.nome || "..."}</Text>
        <Pressable onPress={sair}><Text style={{ color: cores.mut }}>Sair</Text></Pressable>
      </View>

      <View style={st.saldoCard}>
        <Text style={{ color: cores.onp, opacity: 0.82, fontSize: 13 }}>
          Conta {conta?.tipo || ""} · #{conta?.carteira_id ?? "--"}
        </Text>
        <Text style={st.saldo}>{moeda(conta?.saldo || 0)}</Text>
        <View style={{ flexDirection: "row", gap: 12, marginTop: 10 }}>
          <Pressable style={st.acao} onPress={() => navigation.navigate("Transferir")}>
            <Text style={st.acaoTxt}>Transferir</Text>
          </Pressable>
          <Pressable style={st.acao} onPress={() => navigation.navigate("Extrato")}>
            <Text style={st.acaoTxt}>Extrato</Text>
          </Pressable>
        </View>
      </View>

      <Aviso>{erro}</Aviso>

      <Text style={st.secao}>Últimas transações</Text>
      {transacoes.length === 0 ? (
        <Text style={{ color: cores.mut, marginTop: 8 }}>Nenhuma transação ainda.</Text>
      ) : (
        transacoes.map((t) => <ItemTransacao key={t.id} t={t} meuId={conta?.carteira_id} />)
      )}
    </ScrollView>
  );
}

function ItemTransacao({ t, meuId }) {
  const enviada = t.origem_carteira_id === meuId;
  return (
    <View style={st.item}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: cores.ink, fontWeight: "600" }}>
          {enviada ? `Para #${t.destino_carteira_id}` : `De #${t.origem_carteira_id}`}
        </Text>
        {t.aplicou_split ? (
          <Text style={{ color: cores.taxt, fontSize: 12, marginTop: 2 }}>
            Imposto {moeda(t.imposto_total)} → Governo
          </Text>
        ) : null}
      </View>
      <Text style={{ color: enviada ? cores.ink : "#2d7a3f", fontWeight: "600" }}>
        {enviada ? "−" : "+"}{moeda(enviada ? t.valor_bruto : t.liquido)}
      </Text>
    </View>
  );
}

export function TransferirScreen({ navigation }) {
  const [destino, setDestino] = useState("");
  const [valorTxt, setValor] = useState("");
  const [foto, setFoto] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [destinoInfo, setDestinoInfo] = useState(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  const valor = parseValor(valorTxt);
  const exigeSelfie = !isNaN(valor) && valor > LIMITE_FACIAL;

  async function revisar() {
    setErro(""); setPrevia(null); setDestinoInfo(null);
    const id = parseInt(destino, 10);
    if (!id) return setErro("Informe o ID da carteira de destino.");
    if (isNaN(valor) || valor <= 0) return setErro("Informe um valor válido.");
    setCarregando(true);
    try {
      const info = await api.consultarCarteira(id);
      const split = await api.simularSplit(valor, info.tipo);
      setDestinoInfo(info);
      setPrevia(split);
    } catch (e) {
      setErro(e.message);
    } finally {
      setCarregando(false);
    }
  }

  async function confirmar() {
    setErro("");
    if (exigeSelfie && !foto) return setErro(`Transferências acima de ${moeda(LIMITE_FACIAL)} exigem selfie.`);
    setCarregando(true);
    try {
      const t = await api.transferir({
        destino_carteira_id: parseInt(destino, 10),
        valor,
        foto_verificacao_base64: foto || null,
        idempotency_key: `${destino}-${valor}-${Date.now()}`,
      });
      navigation.navigate("Comprovante", { transacao: t });
    } catch (e) {
      setErro(e.message);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 40 }}>
      <Text style={st.titulo}>Transferir</Text>
      <Campo label="Carteira de destino (ID)" keyboardType="numeric" value={destino} onChangeText={(v) => { setDestino(v); setPrevia(null); }} placeholder="Ex: 202" />
      <Campo label="Valor (R$)" keyboardType="decimal-pad" value={valorTxt} onChangeText={(v) => { setValor(v); setPrevia(null); }} placeholder="0,00" />

      {!previa ? (
        <Botao titulo="Revisar" onPress={revisar} carregando={carregando} />
      ) : (
        <>
          <Card style={{ marginTop: 18 }}>
            <Text style={{ color: cores.mut2, marginBottom: 4 }}>
              {destinoInfo?.nome} · {destinoInfo?.tipo}
            </Text>
            <SplitBar liquido={previa.liquido} imposto={previa.imposto_total} altura={16} />
            <View style={{ marginTop: 12 }}>
              <LinhaValor rotulo="Você paga" valor={previa.valor_bruto} />
              {previa.aplicou_split ? (
                <>
                  <LinhaValor rotulo="CBS + IBS → Governo" valor={previa.imposto_total} imposto />
                  <LinhaValor rotulo="Destino recebe" valor={previa.liquido} />
                </>
              ) : (
                <Text style={{ color: cores.mut, fontSize: 13, marginTop: 4 }}>
                  Destino {destinoInfo?.tipo} — sem retenção de imposto.
                </Text>
              )}
            </View>
          </Card>
          {exigeSelfie ? (
            <SelfieButton foto={foto} onCaptura={(f, e) => { setFoto(f); if (e) setErro(e); }} />
          ) : null}
          <Aviso>{erro}</Aviso>
          <Botao titulo="Confirmar transferência" onPress={confirmar} carregando={carregando} />
          <Botao titulo="Voltar" variante="secundario" onPress={() => setPrevia(null)} />
        </>
      )}
      {!previa ? <Aviso>{erro}</Aviso> : null}
    </ScrollView>
  );
}

export function ComprovanteScreen({ route, navigation }) {
  const t = route.params?.transacao;
  if (!t) return null;
  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 48, alignItems: "center" }}>
      <View style={st.check}><Text style={{ fontSize: 40, color: cores.ink }}>✓</Text></View>
      <Text style={{ fontSize: fonte.corpo, color: cores.mut2, marginTop: 16 }}>Transferência enviada</Text>
      <Text style={{ fontSize: fonte.comprovante, fontWeight: "600", color: cores.ink, marginVertical: 8 }}>
        {moeda(t.valor_bruto)}
      </Text>
      <Card style={{ width: "100%", marginTop: 12 }}>
        <LinhaValor rotulo="Bruto" valor={t.valor_bruto} />
        {t.aplicou_split ? (
          <>
            <LinhaValor rotulo="CBS → Governo" valor={t.cbs} imposto />
            <LinhaValor rotulo="IBS → Governo" valor={t.ibs} imposto />
          </>
        ) : null}
        <LinhaValor rotulo="Líquido recebido" valor={t.liquido} />
        <Text style={st.codigo}>#{String(t.id).padStart(6, "0")} · autorizado por {t.auth_metodo}</Text>
      </Card>
      <Botao titulo="Voltar ao início" onPress={() => navigation.navigate("InicioTab")} />
    </ScrollView>
  );
}

export function ExtratoScreen() {
  const [transacoes, setTransacoes] = useState([]);
  const [conta, setConta] = useState(null);
  const [erro, setErro] = useState("");
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const [t, c] = await Promise.all([api.transacoes(), api.minhaConta()]);
      setTransacoes(t);
      setConta(c);
    } catch (e) { setErro(e.message); }
  }, []);
  useFocusEffect(useCallback(() => { carregar(); }, [carregar]));

  return (
    <ScrollView
      style={{ backgroundColor: cores.bg }}
      contentContainerStyle={{ padding: 22, paddingTop: 40 }}
      refreshControl={<RefreshControl refreshing={atualizando} onRefresh={async () => { setAtualizando(true); await carregar(); setAtualizando(false); }} />}
    >
      <Text style={st.titulo}>Extrato</Text>
      <Aviso>{erro}</Aviso>
      {transacoes.length === 0 ? (
        <Text style={{ color: cores.mut, marginTop: 12 }}>Nenhuma transação.</Text>
      ) : (
        transacoes.map((t) => <ItemTransacao key={t.id} t={t} meuId={conta?.carteira_id} />)
      )}
    </ScrollView>
  );
}

export function GovernoScreen() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState("");
  const carregar = useCallback(async () => {
    setErro(""); setDados(null);
    try { setDados(await api.retencoesGoverno()); }
    catch (e) { setErro(e.message); }
  }, []);
  useFocusEffect(useCallback(() => { carregar(); }, [carregar]));

  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 40 }}>
      <Text style={st.titulo}>Governo</Text>
      {erro ? (
        <Aviso tipo="taxt">Visão restrita a administradores. {erro}</Aviso>
      ) : dados ? (
        <>
          <Text style={{ fontSize: fonte.comprovante, fontWeight: "600", color: cores.ink, marginTop: 16 }}>
            {moeda(dados.total)}
          </Text>
          <Text style={{ color: cores.mut2 }}>{dados.transacoes_com_split} transações com split</Text>
          <Card style={{ marginTop: 18 }}>
            <LinhaValor rotulo="CBS retido" valor={dados.cbs_total} imposto />
            <LinhaValor rotulo="IBS retido" valor={dados.ibs_total} imposto />
            <LinhaValor rotulo="Total" valor={dados.total} />
          </Card>
        </>
      ) : null}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  titulo: { fontSize: fonte.tituloTela, fontWeight: "600", color: cores.ink, letterSpacing: -0.5 },
  secao: { fontSize: fonte.corpo, fontWeight: "600", color: cores.ink, marginTop: 24 },
  saldoCard: { backgroundColor: cores.ink, borderRadius: raio.cardPrincipal, padding: 24, marginTop: 18, ...sombraCard },
  saldo: { color: cores.onp, fontSize: fonte.saldo, fontWeight: "600", letterSpacing: -1.4, marginTop: 6 },
  acao: { flex: 1, backgroundColor: "rgba(255,255,255,0.14)", borderRadius: raio.botao, paddingVertical: 12, alignItems: "center" },
  acaoTxt: { color: cores.onp, fontWeight: "600" },
  item: { flexDirection: "row", alignItems: "center", backgroundColor: cores.card, borderRadius: raio.cardMenor, padding: 16, marginTop: 10, ...sombraCard },
  check: { width: 84, height: 84, borderRadius: 42, backgroundColor: cores.tint, alignItems: "center", justifyContent: "center" },
  codigo: { fontFamily: "monospace", fontSize: 12, color: cores.mut, marginTop: 12 },
});
