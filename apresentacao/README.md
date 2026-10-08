# Apresentação Astro — slide 10 com o app REAL embutido

Pasta temporária, separada do projeto (`app/`, `site/`, `backend/` não foram tocados). Pode apagar depois da banca.

## O que é (estado em 2026-10-07, ~22:10)

No slide **10 · A jornada no app**, as 11 telas estáticas foram trocadas por **um celular com o app de verdade dentro**: é o build do `app/` (Vite, modo demonstração, sem `VITE_API_URL`), embutido por `<iframe>`. Clicar em Entrar entra, criar conta cria, e a verificação facial **abre a câmera** (o iframe tem `allow="camera"`).

Ao lado fica o **menu das 11 etapas**, que acompanha o app sozinho:

- lê a rota do app e o que está na tela a cada 350 ms e marca a etapa atual;
- cada etapa alcançada fica **salva** (localStorage `astro-jornada-v2`) e ganha ✓;
- clicar numa etapa leva o app para aquela tela, já na conta certa (pessoal ou da empresa); as setas ← → do slide fazem o mesmo;
- a lua do Astro, pequena e apagada embaixo do menu, recomeça a jornada: zera as etapas, limpa a sessão do app e volta para a boas-vindas.

| # | Etapa | Como o menu detecta |
|---|---|---|
| 01 | Boas-vindas | rota `/bem-vindo` |
| 02 | Login | rota `/login` ou `/criar-conta` |
| 03 | Verificação facial | existe um `<video>` na tela (o clique no menu abre `/login` e toca em "Entrar com biometria") |
| 04 | Início PF | rota `/inicio` sem o card "Imposto das suas vendas" |
| 05 | Pix | rota `/pix` ou `/transferir` |
| 06 | Início PJ | rota `/inicio` com o card "Imposto das suas vendas" |
| 07 | Entenda o split | rota `/split` |
| 08 | Cobrar com nota | rota `/contas` |
| 09 | Equipe & alçadas | rota `/equipe` |
| 10 | Aprovações pendentes | rota `/pendentes` |
| 11 | Comprovante | rota `/extrato` ou `/comprovante/...` |

## Como abrir

```bash
cd apresentacao
py servir.py
# abrir http://localhost:8777/Astro%20Apresentacao.dc.html  e ir ao slide 10
```

Use `servir.py`, não `python -m http.server`: ele devolve o `index.html` do app para as rotas (`/inicio`, `/pix`...). Tem que ser `localhost` (ou https) para o navegador liberar a câmera.

## Arquivos

- `Astro Apresentacao.dc.html` — a apresentação (mudou só o slide 10 e os handlers `jPrev`/`jNext`).
- `astro-app.html` — menu das 11 etapas + moldura do celular com o app dentro.
- `servir.py` — servidor local.
- `index.html`, `assets/`, `welcome/`, ícones — **build do app** (gerado de `app/` com `npm ci && npm run build && node scripts/assemble-www.mjs`). Para atualizar, refaça o build e copie `app/www/*` para cá.
- `support.js`, `image-slot.js`, `site/public/*` — dependências da apresentação.

## Verificado (2026-10-08, Chrome, pelo slide 10)

- Login com e-mail e senha leva ao Início PF e a sessão sobrevive ao recarregar.
- Clicar em cada etapa do menu abre a tela certa e marca a etapa certa, nas 11.
- O menu troca a conta sozinho: etapas 04 e 05 usam a conta pessoal, 06 a 11 a da empresa.
- Etapa 03 abre o login e toca em "Entrar com biometria": a câmera abre e o desafio aparece.
- Etapa 11 marca já no extrato e continua marcada ao abrir um comprovante.
- Setas ← → do slide andam uma etapa por vez.
- Moldura de iPhone com ilha dinâmica; a barra de status e a faixa do indicador seguem a cor da tela do app.
- Teclas ↑ ↓ trocam de slide na apresentação toda, um por vez, inclusive com o foco dentro do celular (no slide 8 a ↓ primeiro avança a animação, como a → já fazia).

## NÃO verificado

- Criar conta do zero (só o login foi percorrido).
- A verificação facial até o fim (a câmera abriu e o desafio apareceu; não concluí os movimentos).
- O MediaPipe pode baixar modelos da internet: testar com a rede da sala da banca.

## Próximos passos

1. Testar a câmera no notebook da apresentação e aceitar a permissão antes da banca.
2. Depois da banca, apagar esta pasta/branch.
