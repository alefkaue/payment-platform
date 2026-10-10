# Astro — app Android

O Astro é **só app Android** (Capacitor): a interface (Vite + TanStack Router em modo SPA)
vai embutida no APK e fala com a API na Azure. **Não há versão web publicada.** Os grupos do
pentest rodam o APK num emulador no PC: `../RODAR-NO-PC.md`.

## Dois apps (productFlavors em `android/app/build.gradle`)

| Sabor | Pacote | Para quê |
|---|---|---|
| `astro` | `com.payflow.app` | O oficial: pinning (`scripts/pinos.mjs`), atestação da chave no Keystore, sem print (`FLAG_SECURE`), sem depuração do WebView |
| `lab` | `com.payflow.app.lab` | Pentest: aceita CA do usuário (Burp/ZAP), sem pinning, print e `chrome://inspect` liberados, não manda atestação (`src/lab/`) |

O CI (`.github/workflows/android.yml`) gera os dois. Uma tag `apk-vX.Y` publica um
**GitHub Release** com `Astro.apk`, `Astro-Lab.apk` e `SHA256SUMS.txt`:

```bash
git tag apk-v1.0 && git push origin apk-v1.0
```

## Desenvolver

```bash
npm run dev          # no navegador do PC, só para desenvolver (http://localhost:8081)
```

O navegador serve para desenvolver a interface; o produto é o APK. Recursos nativos
(botão Voltar, barra de status, rede, chave no Keystore) só existem no app.

## Versão .apk (Android)

O projeto Android já está gerado em `android/`. Para **compilar o .apk** é preciso
ter o toolchain Android na máquina (não vem neste repositório):

- **JDK 21** e **Android SDK** (o jeito fácil é instalar o **Android Studio**). O CI usa JDK 21.

Com isso instalado:

```bash
npm run build:mobile          # atualiza www/ e sincroniza com android/
cd android && ./gradlew assembleDebug
# .apk em: android/app/build/outputs/apk/debug/app-debug.apk
```

Ou abra a pasta `android/` no **Android Studio** e clique em *Run* (gera e instala
no celular/emulador direto).

> Para um **.apk de produção assinado**, use `assembleRelease` com um keystore,
> ou um serviço de build em nuvem.

### Testar no celular agora, sem compilar

Com `npm run dev` rodando, abra no navegador do celular (mesma rede Wi‑Fi):
`http://SEU_IP_LOCAL:8081` — é o app idêntico ao que vira apk.
