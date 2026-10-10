# Astro — relatório da rodada "só celular" e do trabalho Claude + Codex (10/10/2026)

> Arquivo de passagem de bastão. Escrito pelo Claude Code e atualizado ao longo do trabalho,
> para o Alef ler ao voltar. **Estado: ver a seção 5 (andamento).**

## 1. Como o trabalho foi organizado

- **Claude Code** coordena, faz backend, infra e CI, revisa e junta tudo na `main`.
- **Codex (GPT)** faz frontend/app, ataques à API e revisão independente do Claude
  (instruções em `GPT.md`). Roda em pastas separadas (`../astro-gpt`, `../astro-gpt2`, git
  worktrees) e **não faz commit** (o sandbox não deixa escrever no `.git` principal); o Claude
  revisa o diff, faz o commit e o merge.
- Codex no Windows: usar **`C:\codex\codex.cmd`** (a instalação padrão tem caminho longo demais
  para o sandbox "elevated" do Windows).
- **Gemini**: sem uso (a chave de API gratuita tem 20 pedidos/dia e acabou no 1º cartão).

## 2. Segurança (auditoria 2) — concluída e no GitHub

Relatório completo: `relatorios/AUDITORIA-2-SEGURANCA.md`. Resumo: 30 achados corrigidos, cada
um com teste que falha sem a correção (pagamento duplicado em reenvio de Pix/folha/lote/
pendências, colisão de chave do cliente com chave interna, teto de aparelho novo contornável,
Pix Automático sem limites, NF-e repetida, MED + devolução em dobro, erro 500 por chave longa
no Postgres…), revisão cruzada entre os agentes, fuzz de invariantes (o dinheiro nunca nasce
nem some) e concorrência real no Postgres. A-15 (TOTP do admin) e A-16 (troca/recuperação de
senha) feitos.

## 3. Lógica bancária (relatório R1) — feito até aqui

`relatorios/R1-logica-bancaria.md` (comparação com bancos reais e BCB). Já corrigido:
- **Split com transição honesta** (sua escolha): 2026 mostra o imposto da nota e não retém;
  retenção a partir de `SPLIT_RETENCAO_DESDE` (2027-01-01); `SPLIT_DEMONSTRACAO=1` para a
  apresentação, com selo "Simulação" (proibido em produção).
- **Devolução de Pix** por quem recebeu (até 90 dias, parcial ou total).
- Apuração do mês de verdade; "A receber" sem cobranças pagas; saldo bloqueado visível;
  folha demo com lançamentos; rendimento não retroativo; comprovante com imposto da nota.
- **Falta** (itens maiores): comprovante com ID E2E e QR Code BR Code, Pix Agendado, IR/IOF
  no rendimento, extrato exportável, encerramento de conta, KYB completo.

## 4. "Só celular" (pedido de hoje) — decisões do Claude

Você pediu para tirar a web e deixar só celular, e deixou as decisões comigo:
- **Só Android.** iPhone fora do escopo (sem Mac/conta Apple; sem web não há PWA).
- **Sem app web.** O Static Web Apps da Azure publica só uma **página de download**
  (`download/`, HTML estático, CSP fechada). O CORS da API só libera a origem do APK.
- **Dois APKs** (Gradle `productFlavors`):
  - **Astro** (`com.payflow.app`): o oficial, endurecido (pinning, atestação, sem print, sem
    depuração).
  - **Astro Lab** (`com.payflow.app.lab`): para o pentest — aceita a CA do Burp/ZAP, sem
    pinning, print e `chrome://inspect` liberados, não manda atestação. Mesma API.
- **Distribuição**: o CI gera os dois; uma tag `apk-vX.Y` publica um **GitHub Release** com
  `Astro.apk`, `Astro-Lab.apk` e `SHA256SUMS.txt` (links fixos `releases/latest/download/...`).
- **Guia para os grupos**: `RODAR-NO-PC.md` (Android Studio com a webcam como câmera, Burp,
  Frida; LDPlayer/BlueStacks como alternativa).
- **Ambiente do pentest**: `ATESTACAO_EXIGIDA=0` (emulador não tem chip de segurança); todo o
  resto vale igual.
- Plugins oficiais do Capacitor instalados (app, network, status-bar, keyboard) para o
  comportamento de app Android.

## 5. Andamento

| Etapa | Situação |
|---|---|
| Gradle (dois APKs), CI com Release, Azure só com página de download, plugins | ✅ feito (commit `b11075c`) |
| `RODAR-NO-PC.md`, `PENTEST.md`, `MOBILE.md`, `AZURE.md`, README | ✅ feito (commit `2ca6549`) |
| App se comportar como Android (botão Voltar, áreas seguras, teclado, rede ruim, câmera traseira) | ⏳ com a Codex (cartão M1) |
| Tag `apk-v1.0` (primeiro Release com os APKs) | ⏳ depois do M1 |

## 6. O que depende de você

- **Ver o CI** depois do envio (aba Actions do GitHub): o build Android com os dois sabores e o
  Release não puderam ser testados nesta máquina (não há Android SDK nem `az`/Bicep aqui).
- **Testar num emulador** seguindo `RODAR-NO-PC.md` (principalmente a prova de vida pela webcam).
- **Azure**: subir o ambiente (`AZURE.md`) com `ATESTACAO_EXIGIDA=0` e preencher a variável
  `ASTRO_API_URL` no GitHub, senão o APK sai em modo demonstração.
- Preencher período e contato no `PENTEST.md`.
