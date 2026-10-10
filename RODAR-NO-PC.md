# Rodar o Astro no PC (emulador Android)

O Astro é um **banco de celular**: não existe versão web. No computador, você roda o app
Android num **emulador**. Este guia é para quem vai usar o app ou fazer o pentest
(regras em `PENTEST.md`).

**Baixar os apps** (sempre a versão mais nova):

| App | Para quê | Link |
|---|---|---|
| **Astro** | O app oficial, com todas as proteções (pinning, atestação, sem print, sem depuração) | [Astro.apk](https://github.com/alefkaue/payment-platform/releases/latest/download/Astro.apk) |
| **Astro Lab** | Pentest: aceita a CA do Burp/ZAP, permite print e depurar o WebView, não usa atestação | [Astro-Lab.apk](https://github.com/alefkaue/payment-platform/releases/latest/download/Astro-Lab.apk) |
| Conferência | SHA-256 dos dois arquivos | [SHA256SUMS.txt](https://github.com/alefkaue/payment-platform/releases/latest/download/SHA256SUMS.txt) |

Os dois falam com a **mesma API** e podem ficar instalados juntos.

---

## Opção A — Android Studio (recomendada, a melhor para pentest)

**Antes:** Windows 10/11 com **virtualização ligada** na BIOS (Intel VT-x / AMD-V), 8 GB de
RAM ou mais e ~15 GB livres. No Windows, ligue também *Plataforma do Hipervisor do Windows*
(Painel de Controle → Programas → Ativar ou desativar recursos do Windows).

1. Instale o [Android Studio](https://developer.android.com/studio) (só o padrão; não precisa abrir projeto).
2. Na tela inicial: **More Actions → Virtual Device Manager → Create Virtual Device**.
3. Escolha um celular (ex.: **Pixel 8**) → **Next**.
4. Imagem do sistema: **Android 15 (API 35)** do tipo **Google APIs** (sem "Play Store").
   *Por quê:* a imagem sem Play Store aceita `adb root`, que o Frida precisa.
5. **Show Advanced Settings → Camera**: **Front = Webcam0** e **Back = Webcam0**.
   *Por quê:* o login e o cadastro pedem a **prova de vida com o rosto**; a webcam do PC
   vira a câmera do celular.
6. **Finish** e aperte ▶ para ligar o emulador.
7. **Instalar o app**: arraste o `.apk` para a janela do emulador (ou `adb install Astro-Lab.apk`).
8. Abra o **Astro** (ou **Astro Lab**), crie a conta com seu nome, CPF, documento (foto da
   frente e do verso pela câmera) e a prova de vida. Pronto.

### Ler o tráfego com o Burp (só no Astro Lab)

1. No Burp: *Proxy → Options*: listener em `127.0.0.1:8080`.
2. No emulador: **⋯ (Extended controls) → Settings → Proxy** → *Manual proxy configuration*:
   host `127.0.0.1`, porta `8080` → **Apply**.
3. Exporte o certificado do Burp (*Proxy → Options → Import/export CA certificate → Certificate
   in DER format*), salve como `burp.cer` e arraste para o emulador.
4. No Android: **Configurações → Segurança → Mais configurações de segurança → Criptografia
   e credenciais → Instalar um certificado → Certificado de CA** → escolha `burp.cer`.
5. Abra o **Astro Lab**: o tráfego da API aparece no Burp. (O **Astro** oficial recusa esse
   certificado de propósito: o pinning faz parte do que vocês podem tentar quebrar.)

### Frida (opcional)

```sh
adb root                       # só funciona na imagem "Google APIs" (sem Play Store)
adb push frida-server /data/local/tmp/ && adb shell chmod 755 /data/local/tmp/frida-server
adb shell /data/local/tmp/frida-server &
frida -U -n "Astro Lab"
```

O WebView do **Astro Lab** também aparece no `chrome://inspect` do Chrome do PC.

---

## Opção B — LDPlayer ou BlueStacks (mais leve, menos controle)

1. Instale o [LDPlayer](https://www.ldplayer.net/) ou o [BlueStacks](https://www.bluestacks.com/).
2. Arraste o `.apk` para a janela.
3. Habilite a câmera do PC nas configurações do emulador (o nome muda de versão para versão).

Serve para **usar** o app. Para **atacar**, a Opção A é mais previsível (proxy, root e Frida
funcionam do jeito documentado acima).

---

## O que esperar no emulador

- **Atestação do aparelho**: o emulador não tem chip de segurança (TEE/StrongBox), então o
  app entra como "aparelho sem atestação". No ambiente do pentest isso é **permitido**
  (`ATESTACAO_EXIGIDA=0`); todo o resto (senha + rosto, DPoP, sessões, limites, alçadas)
  continua valendo. Fazer um aparelho modificado parecer íntegro é um achado (`PENTEST.md`).
- **Prova de vida**: funciona com a webcam. Fique de frente, com boa luz, e faça só o que a
  tela pede.
- **Print de tela**: bloqueado no Astro oficial (proteção contra trojans bancários);
  liberado no Astro Lab, para as evidências do relatório.

## iPhone

Fora do escopo por enquanto: um app de iPhone exige um Mac e uma conta Apple Developer, e o
Astro não tem versão web. Use o emulador Android.

## Problemas comuns

| Sintoma | Causa / solução |
|---|---|
| Emulador não liga ou fica muito lento | Virtualização desligada na BIOS ou Hipervisor do Windows desligado |
| "Câmera indisponível" na prova de vida | Em Advanced Settings, a câmera não está como **Webcam0**; ou outro programa está usando a webcam |
| "App não instalado" | Já existe uma versão assinada por outra chave: desinstale a anterior e instale de novo |
| Astro Lab sem tráfego no Burp | Proxy do emulador não aplicado ou CA do Burp não instalada como **Certificado de CA** |
| Erro de conexão no Astro oficial com o Burp ligado | Esperado: o pinning recusa o certificado do Burp. Use o Astro Lab |
