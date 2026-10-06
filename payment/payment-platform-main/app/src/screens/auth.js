import React, { useContext, useState } from "react";
import { ScrollView, Text, View, Pressable, StyleSheet } from "react-native";
import { Botao, Campo, Aviso, Card, SelfieButton, SplitBar } from "../components";
import { Logo } from "../logo";
import { AuthContext } from "../auth";
import { api } from "../api";
import { cores, fonte, raio, moeda } from "../theme";

export function LandingScreen({ navigation }) {
  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 64 }}>
      <Logo tamanho={22} />
      <Card style={{ marginTop: 28 }}>
        <Text style={{ color: cores.mut2, fontSize: fonte.secundario, marginBottom: 10 }}>
          Exemplo de split para empresa (PJ)
        </Text>
        <SplitBar liquido={990} imposto={10} altura={16} />
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 12 }}>
          <Text style={{ color: cores.mut }}>Bruto {moeda(1000)}</Text>
          <Text style={{ color: cores.taxt }}>Imposto {moeda(10)}</Text>
          <Text style={{ color: cores.ink, fontWeight: "600" }}>Líquido {moeda(990)}</Text>
        </View>
      </Card>
      <Text style={{ fontSize: fonte.tituloLanding, fontWeight: "600", color: cores.ink, marginTop: 32, lineHeight: 40 }}>
        Pagamentos que já chegam com o imposto certo.
      </Text>
      <Text style={{ fontSize: fonte.corpo, color: cores.mut2, marginTop: 10, lineHeight: 22 }}>
        Split automático de IBS/CBS da Reforma Tributária. Para empresas, o imposto vai
        direto ao Governo e o líquido cai na conta — no ato.
      </Text>
      <Botao titulo="Abrir conta" onPress={() => navigation.navigate("Registrar")} />
      <Botao titulo="Já tenho conta" variante="secundario" onPress={() => navigation.navigate("Login")} />
    </ScrollView>
  );
}

export function LoginScreen() {
  const { entrar } = useContext(AuthContext);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function fazerLogin() {
    setErro("");
    setCarregando(true);
    try {
      await api.login(email.trim(), senha);
      await entrar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 40 }}>
      <Text style={st.titulo}>Bem-vindo de volta</Text>
      <Campo label="E-mail" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} placeholder="voce@email.com" />
      <Campo label="Senha" secureTextEntry value={senha} onChangeText={setSenha} placeholder="••••••••" />
      <Aviso>{erro}</Aviso>
      <Botao titulo="Entrar" onPress={fazerLogin} carregando={carregando} />
    </ScrollView>
  );
}

export function RegistrarScreen() {
  const { entrar } = useContext(AuthContext);
  const [tipo, setTipo] = useState("PF");
  const [form, setForm] = useState({ nome: "", email: "", senha: "", documento: "" });
  const [foto, setFoto] = useState(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  async function registrar() {
    setErro("");
    if (!foto) return setErro("Tire a selfie de cadastro (biometria).");
    if ((form.senha || "").length < 8) return setErro("A senha precisa ter ao menos 8 caracteres.");
    setCarregando(true);
    try {
      await api.registrar({
        nome: form.nome.trim(),
        email: form.email.trim(),
        senha: form.senha,
        tipo,
        documento: form.documento.trim() || null,
        foto_rosto_base64: foto,
      });
      await api.login(form.email.trim(), form.senha);
      await entrar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <ScrollView style={{ backgroundColor: cores.bg }} contentContainerStyle={{ padding: 22, paddingTop: 40 }}>
      <Text style={st.titulo}>Criar conta</Text>
      <View style={{ flexDirection: "row", gap: 10, marginTop: 16 }}>
        {["PF", "PJ"].map((t) => (
          <Pressable
            key={t}
            onPress={() => setTipo(t)}
            style={[st.toggle, tipo === t && { backgroundColor: cores.ink, borderColor: cores.ink }]}
          >
            <Text style={{ color: tipo === t ? cores.onp : cores.mut2, fontWeight: "600" }}>
              {t === "PF" ? "Pessoa física" : "Empresa (PJ)"}
            </Text>
          </Pressable>
        ))}
      </View>
      <Campo label="Nome" value={form.nome} onChangeText={set("nome")} placeholder={tipo === "PF" ? "Seu nome" : "Razão social"} />
      <Campo label="E-mail" autoCapitalize="none" keyboardType="email-address" value={form.email} onChangeText={set("email")} placeholder="voce@email.com" />
      <Campo label="Senha" secureTextEntry value={form.senha} onChangeText={set("senha")} placeholder="mínimo 8 caracteres" />
      <Campo label={tipo === "PF" ? "CPF" : "CNPJ"} keyboardType="numeric" value={form.documento} onChangeText={set("documento")} placeholder={tipo === "PF" ? "000.000.000-00" : "00.000.000/0000-00"} />
      <SelfieButton foto={foto} onCaptura={(f, e) => { setFoto(f); if (e) setErro(e); }} label="Tirar selfie de cadastro" />
      <Text style={st.dicaSelfie}>Rosto de frente, sem óculos escuros, lugar iluminado, só você na foto.</Text>
      <Aviso>{erro}</Aviso>
      <Botao titulo="Criar conta" onPress={registrar} carregando={carregando} />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  titulo: { fontSize: fonte.tituloTela, fontWeight: "600", color: cores.ink, letterSpacing: -0.5 },
  toggle: { flex: 1, borderWidth: 1.5, borderColor: cores.line2, borderRadius: raio.botao, paddingVertical: 14, alignItems: "center" },
  dicaSelfie: { fontSize: 11.5, color: cores.mut, marginTop: 8 },
});
