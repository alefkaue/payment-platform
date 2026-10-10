# Rodar o Astro no PC (emulador Android)

O Astro é um **banco de celular**. No computador, você roda o app Android num **emulador**.
(Existe também uma versão web, só para testes rápidos da equipe; o produto é o app.) Este guia é para quem vai usar o app ou fazer o pentest
(regras em `PENTEST.md`).

**Baixar os apps** (sempre a versão mais nova):

| Arquivo | Link |
|---|---|
| **Astro** (app Android) | [Astro.apk](https://github.com/alefkaue/payment-platform/releases/latest/download/Astro.apk) |
| Conferência (SHA-256) | [SHA256SUMS.txt](https://github.com/alefkaue/payment-platform/releases/latest/download/SHA256SUMS.txt) |

O app tem as proteções de um banco ligadas (pinning, atestação, sem print, sem depuração):
vencê-las faz parte do desafio.

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
7. **Instalar o app**: arraste o `.apk` para a janela do emulador (ou `adb install Astro.apk`).
8. Abra o **Astro**, crie a conta com seu nome, CPF, documento (foto da
   frente e do verso pela câmera) e a prova de vida. Pronto.

### Ler o tráfego (Burp/ZAP)

Configure o proxy do emulador (**⋯ → Settings → Proxy**, host `127.0.0.1`, porta do Burp) e
instale a CA do Burp no Android. O app **recusa** essa CA de propósito (certificate pinning e
só CAs do sistema): passar por essa proteção é parte do desafio.

### Frida (opcional)

```sh
adb root                       # só funciona na imagem "Google APIs" (sem Play Store)
adb push frida-server /data/local/tmp/ && adb shell chmod 755 /data/local/tmp/frida-server
adb shell /data/local/tmp/frida-server &
frida -U -n "Astro"
```


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
- **Print de tela**: bloqueado no app (proteção contra trojans bancários). Para evidências,
  use o print do próprio emulador (botão de câmera nos controles do Android Studio).

## iPhone

Sem app de iPhone por enquanto (exige um Mac e uma conta Apple Developer). Use o emulador
Android.

## Problemas comuns

| Sintoma | Causa / solução |
|---|---|
| Emulador não liga ou fica muito lento | Virtualização desligada na BIOS ou Hipervisor do Windows desligado |
| "Câmera indisponível" na prova de vida | Em Advanced Settings, a câmera não está como **Webcam0**; ou outro programa está usando a webcam |
| "App não instalado" | Já existe uma versão assinada por outra chave: desinstale a anterior e instale de novo |
| Erro de conexão com o Burp ligado | Esperado: o pinning recusa o certificado do Burp (parte do desafio) |
