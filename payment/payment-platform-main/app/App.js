import React, { useContext } from "react";
import { StatusBar } from "expo-status-bar";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";

import { AuthProvider, AuthContext } from "./src/auth";
import { LandingScreen, LoginScreen, RegistrarScreen } from "./src/screens/auth";
import { InicioScreen, TransferirScreen, ComprovanteScreen, ExtratoScreen, GovernoScreen } from "./src/screens/main";
import { cores } from "./src/theme";

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const tema = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: cores.bg, primary: cores.ink, card: cores.card, text: cores.ink, border: cores.line },
};

const opcoesTela = {
  headerStyle: { backgroundColor: cores.bg },
  headerShadowVisible: false,
  headerTintColor: cores.ink,
  headerTitle: "",
  contentStyle: { backgroundColor: cores.bg },
};

function Tabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: cores.ink,
        tabBarInactiveTintColor: cores.mut3,
        tabBarStyle: { backgroundColor: cores.card, borderTopColor: cores.line, height: 60, paddingBottom: 8, paddingTop: 6 },
      }}
    >
      <Tab.Screen name="InicioTab" component={InicioScreen} options={{ title: "Início" }} />
      <Tab.Screen name="Extrato" component={ExtratoScreen} options={{ title: "Extrato" }} />
      <Tab.Screen name="Governo" component={GovernoScreen} options={{ title: "Governo" }} />
    </Tab.Navigator>
  );
}

function Rotas() {
  const { logado } = useContext(AuthContext);
  return (
    <Stack.Navigator screenOptions={opcoesTela}>
      {logado ? (
        <>
          <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
          <Stack.Screen name="Transferir" component={TransferirScreen} />
          <Stack.Screen name="Comprovante" component={ComprovanteScreen} options={{ headerShown: false }} />
        </>
      ) : (
        <>
          <Stack.Screen name="Landing" component={LandingScreen} options={{ headerShown: false }} />
          <Stack.Screen name="Login" component={LoginScreen} options={{ title: "Entrar" }} />
          <Stack.Screen name="Registrar" component={RegistrarScreen} options={{ title: "Criar conta" }} />
        </>
      )}
    </Stack.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer theme={tema}>
        <StatusBar style="dark" />
        <Rotas />
      </NavigationContainer>
    </AuthProvider>
  );
}
