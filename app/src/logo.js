import React from "react";
import { Text, View } from "react-native";
import { cores } from "./theme";

// Logo = wordmark "payflow" com a bola amarela substituindo o "o" (ver marca do
// handoff). Em RN fazemos com Views; a bola é um círculo âmbar.
export function Logo({ tamanho = 22, cor }) {
  const d = tamanho * 0.56;
  const corTexto = cor || cores.ink;
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <Text style={{ fontSize: tamanho, fontWeight: "700", color: corTexto, letterSpacing: -tamanho * 0.05 }}>
        payfl
      </Text>
      <View
        style={{
          width: d, height: d, borderRadius: d / 2, backgroundColor: cores.marca,
          marginHorizontal: 1, marginBottom: -tamanho * 0.02,
        }}
      />
      <Text style={{ fontSize: tamanho, fontWeight: "700", color: corTexto, letterSpacing: -tamanho * 0.05 }}>
        w
      </Text>
    </View>
  );
}
