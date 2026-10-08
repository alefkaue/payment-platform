# Apresentação Astro — slide 10 com o app REAL embutido

Pasta temporária, separada do projeto (`app/`, `site/`, `backend/` não foram tocados). Pode apagar depois da banca.

## O que é (estado em 2026-10-07, ~22:10)

No slide **10 · A jornada no app**, as 11 telas estáticas foram trocadas por **um celular com o app de verdade dentro**: é o build do `app/` (Vite, modo demonstração, sem `VITE_API_URL`), embutido por `<iframe>`. Clicar em Entrar entra, criar conta cria, e a verificação facial **abre a câmera** (o iframe tem `allow="camera"`).

Ao lado fica o **menu das 11 etapas**, que acompanha o app sozinho:

- lê a rota do app e o que está na tela a cada 350 ms e marca a etapa atual;
- cada etapa alcançada fica **salva** (localStorage `astro-jornada-v2`) e ganha ✓;
- clicar numa etapa leva o app para aquela tela; as setas ← → do slide fazem o mesmo;
- "Recomeçar a jornada" limpa a sessão do app e volta para a boas-vindas.

| # | Etapa | Como o menu detecta |
|---|---|---|
| 01 | Boas-vindas | rota `/bem-vindo` |
| 02 | Login | rota `/login` ou `/criar-conta` |
| 03 | Verificação facial | existe um `<video>` na tela (câmera aberta) |
| 04 | Início PF | rota `/inicio` sem o card "Imposto das suas vendas" |
| 05 | Pix | rota `/pix` ou `/transferir` |
| 06 | Início PJ | rota `/inicio` com o card "Imposto das suas vendas" |
| 07 | Entenda o split | rota `/split` |
| 08 | Cobrar com nota | rota `/contas` |
| 09 | Equipe & alçadas | rota `/equipe` |
| 10 | Aprovações pendentes | rota `/pendentes` |
| 11 | Comprovante | rota `/comprovante/...` (o clique no menu abre `/extrato`) |

## Como abrir

```bash
cd apresentacao
python servir.py
# abrir http://localhost:8777/Astro%20Apresentacao.dc.html  e ir ao slide 10
```

Use `servir.py`, não `python -m http.server`: ele devolve o `index.html` do app para as rotas (`/inicio`, `/pix`...). Tem que ser `localhost` (ou https) para o navegador liberar a câmera.

## Arquivos

- `Astro Apresentacao.dc.html` — a apresentação (mudou só o slide 10 e os handlers `jPrev`/`jNext`).
- `astro-app.html` — menu das 11 etapas + moldura do celular com o app dentro.
- `servir.py` — servidor local.
- `index.html`, `assets/`, `welcome/`, ícones — **build do app** (gerado de `app/` com `npm ci && npm run build && node scripts/assemble-www.mjs`). Para atualizar, refaça o build e copie `app/www/*` para cá.
- `support.js`, `image-slot.js`, `site/public/*` — dependências da apresentação.

## Verificado

- Build do app sem erro; o app real aparece dentro do celular (captura no Edge sem janela) e o menu marca "01 Boas-vindas".
- A apresentação renderiza o iframe do slide 10 com `allow="camera"`.

## NÃO verificado (parei por causa do horário, 22:15)

- Jornada completa clique a clique no slide: login, criar conta, **câmera na verificação facial**, troca PF → PJ.
- Se o menu detecta certo as etapas 03 (câmera) e 06 (Início PJ) — foi escrito pela leitura do código, não testado ao vivo.
- Clicar numa etapa do menu recarrega o app naquela rota; não confirmei que a sessão sobrevive ao recarregar.
- O MediaPipe da verificação facial pode baixar modelos da internet: testar com a rede da sala da banca.

## Próximos passos

1. Percorrer as 11 etapas no slide e corrigir a detecção do menu onde errar.
2. Testar a câmera no notebook da apresentação e aceitar a permissão antes da banca.
3. Depois da banca, apagar esta pasta/branch.
