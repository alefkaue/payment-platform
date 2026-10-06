import React from "react";
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  View,
  StyleSheet,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { cores, raio, fonte, sombraCard, moeda } from "./theme";

export function Botao({ titulo, onPress, variante = "primario", carregando, desabilitado }) {
  const primario = variante === "primario";
  return (
    <Pressable
      onPress={onPress}
      disabled={desabilitado || carregando}
      style={({ pressed }) => [
        s.botao,
        primario ? s.botaoPrimario : s.botaoSecundario,
        (desabilitado || carregando) && { opacity: 0.5 },
        pressed && { transform: [{ translateY: 1 }] },
      ]}
    >
      {carregando ? (
        <ActivityIndicator color={primario ? cores.onp : cores.ink} />
      ) : (
        <Text style={[s.botaoTexto, { color: primario ? cores.onp : cores.ink }]}>{titulo}</Text>
      )}
    </Pressable>
  );
}

export function Campo({ label, dica, ...props }) {
  return (
    <View style={{ marginTop: 14 }}>
      {label ? <Text style={s.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={cores.mut3}
        style={s.input}
        {...props}
      />
      {dica ? <Text style={s.dica}>{dica}</Text> : null}
    </View>
  );
}

export function Aviso({ tipo = "erro", children }) {
  if (!children) return null;
  const erro = tipo === "erro";
  return (
    <View style={[s.aviso, { backgroundColor: erro ? cores.errbg : cores.taxbg }]}>
      <Text style={{ color: erro ? cores.errt : cores.taxt, fontSize: fonte.secundario }}>{children}</Text>
    </View>
  );
}

export function Card({ children, style }) {
  return <View style={[s.card, style]}>{children}</View>;
}

// Barra do split: preto = líquido, âmbar = imposto.
export function SplitBar({ liquido, imposto, altura = 14 }) {
  const total = Number(liquido) + Number(imposto);
  const pLiq = total > 0 ? (Number(liquido) / total) * 100 : 100;
  return (
    <View style={{ flexDirection: "row", height: altura, borderRadius: raio.barra, overflow: "hidden", gap: 2 }}>
      <View style={{ width: `${pLiq}%`, backgroundColor: cores.ink }} />
      <View style={{ flex: 1, backgroundColor: cores.ocre }} />
    </View>
  );
}

export function LinhaValor({ rotulo, valor, imposto }) {
  return (
    <View style={s.linhaValor}>
      <Text style={{ color: imposto ? cores.taxt : cores.mut2, fontSize: fonte.corpo }}>{rotulo}</Text>
      <Text style={{ color: imposto ? cores.taxt : cores.ink, fontSize: fonte.corpo, fontWeight: "600" }}>
        {moeda(valor)}
      </Text>
    </View>
  );
}

// Botão que abre a câmera frontal e devolve a foto em base64 (data URI).
export function SelfieButton({ onCaptura, foto, label = "Tirar selfie de verificação" }) {
  async function capturar() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      onCaptura(null, "Permissão de câmera negada. Libere nas configurações.");
      return;
    }
    const r = await ImagePicker.launchCameraAsync({
      cameraType: ImagePicker.CameraType.front,
      quality: 0.6,
      base64: true,
    });
    if (r.canceled) return;
    const a = r.assets[0];
    onCaptura(`data:image/jpeg;base64,${a.base64}`, null);
  }
  return (
    <Pressable onPress={capturar} style={[s.selfie, foto && { borderColor: cores.ink }]}>
      <Text style={{ color: foto ? cores.ink : cores.mut2, fontWeight: "600" }}>
        {foto ? "✓ Selfie capturada (toque para refazer)" : label}
      </Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  botao: { borderRadius: raio.botao, paddingVertical: 16, alignItems: "center", justifyContent: "center", marginTop: 16 },
  botaoPrimario: { backgroundColor: cores.ink },
  botaoSecundario: { backgroundColor: cores.tint },
  botaoTexto: { fontSize: fonte.corpo, fontWeight: "600" },
  label: { fontSize: fonte.label, fontWeight: "600", color: cores.mut2, marginBottom: 6 },
  input: {
    backgroundColor: cores.card, borderWidth: 1.5, borderColor: cores.line,
    borderRadius: raio.input, paddingVertical: 14, paddingHorizontal: 16, fontSize: fonte.corpo, color: cores.ink,
  },
  dica: { fontSize: 11.5, color: cores.mut, marginTop: 5 },
  aviso: { marginTop: 14, padding: 12, borderRadius: raio.aviso },
  card: { backgroundColor: cores.card, borderRadius: raio.cardPrincipal, padding: 22, ...sombraCard },
  linhaValor: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  selfie: {
    marginTop: 14, borderWidth: 1.5, borderColor: cores.line2, borderStyle: "dashed",
    borderRadius: raio.input, paddingVertical: 18, alignItems: "center",
  },
});
