# Astro — relatório da rodada "só celular" e do trabalho Claude + Codex (10/10/2026)

> Arquivo de passagem de bastão. Escrito pelo Claude Code e atualizado ao longo do trabalho,
> para o Alef ler ao voltar. **Estado: tudo concluído e no GitHub (seção 5).**

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
| Gradle (dois APKs), CI com Release, Azure só com página de download, plugins | ✅ feito (commit `b11075c`); **build dos dois APKs passou no CI do GitHub** |
| `RODAR-NO-PC.md`, `PENTEST.md`, `MOBILE.md`, `AZURE.md`, README | ✅ feito (commit `2ca6549`) |
| App se comportar como Android (botão Voltar, áreas seguras, teclado, rede ruim, câmera traseira) | ✅ feito pela Codex, revisado e juntado (commit `8e6baa2`); app 157 testes |
| Tag `apk-v1.0` (primeiro Release com os APKs) | ✅ [Release apk-v1.0](https://github.com/alefkaue/payment-platform/releases/tag/apk-v1.0) com `Astro.apk`, `Astro-Lab.apk` e `SHA256SUMS.txt` |

### Detalhes do M1 (app com comportamento de Android)

- **Botão Voltar**: fecha primeiro o que está aberto (menu "Mais", câmera, confirmações); senão
  volta a tela; no Início/Login pede um segundo toque para sair.
- **Áreas seguras** (notch e barra de gestos) e barra de status na cor do app.
- **Teclado certo** em cada campo (numérico em valores/CPF, e-mail em e-mail) sem cobrir o botão.
- **Sem conexão**: faixa no topo e botões que movem dinheiro desabilitados.
- **Câmera**: traseira no documento, frontal na prova de vida.
- **Sessão no celular só na memória**: se o Android fechar o app, entra de novo com senha e
  rosto (como os bancos reais).

## 6. O que depende de você

- O CI do GitHub **passou**: backend (com Postgres), build dos dois APKs e o Release. O que não
  pôde ser testado aqui: o app rodando num emulador/celular de verdade e o Bicep compilado (não há
  Android SDK nem `az`/Bicep nesta máquina).
- **Testar num emulador** seguindo `RODAR-NO-PC.md` (principalmente a prova de vida pela webcam).
- **Importante — os APKs do `apk-v1.0` estão em modo demonstração** (dados fictícios no próprio
  aparelho, sem API) e assinados com a chave de debug: a Azure ainda não está no ar, então não
  existe `ASTRO_API_URL`. Quando subir a Azure (`AZURE.md`, com `ATESTACAO_EXIGIDA=0`):
  1. GitHub → Settings → Variables → `ASTRO_API_URL` = a `apiUrl` do Front Door;
  2. (recomendado) secrets da chave de assinatura (`AZURE.md` §4, `chave_apk.py`);
  3. `git tag apk-v1.1 && git push origin apk-v1.1` → sai o Release ligado à API de verdade.
  Os links `releases/latest/download/...` do `RODAR-NO-PC.md` passam a apontar para ele sozinhos.
- Preencher período e contato no `PENTEST.md`.
