# PayFlow — app web + .apk (um código só)

O mesmo app (Vite + TanStack Router em **modo SPA**) roda como **web** e como
**.apk Android** (via [Capacitor](https://capacitorjs.com)). Não há duplicação de
código: o build gera um SPA estático e o Capacitor o embute no app nativo.

## Versão web (simulação do app no navegador)

```bash
npm run dev          # desenvolvimento (http://localhost:8081)
# ou a build estática (igual à que vai pro apk):
npm run build:mobile # gera www/ (SPA estático)
npm run preview:mobile  # serve em http://localhost:8099
```

`www/` é 100% estático (dados mockados no cliente) — pode ser hospedado em
qualquer lugar (Vercel, Netlify, GitHub Pages) como a "simulação web" do app.

## Versão .apk (Android)

O projeto Android já está gerado em `android/`. Para **compilar o .apk** é preciso
ter o toolchain Android na máquina (não vem neste repositório):

- **JDK 17** e **Android SDK** (o jeito fácil é instalar o **Android Studio**).

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
