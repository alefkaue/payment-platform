# Publicar a apresentação da Astro (guia para o Claude de quem for publicar)

> Leia tudo antes de agir. O objetivo é **um link `https://` público** que abra a
> apresentação no notebook e o app no celular, com **Pix funcionando entre os dois
> aparelhos**. Não é preciso backend, servidor próprio, túnel nem admin no PC.

## 1. O que está pronto nesta pasta (`apresentacao/`, branch `apresentacao-interativa`)

É um **site estático**, já montado. Não precisa de build para publicar.

| Arquivo | O que é |
|---|---|
| `apresentacao.html` | A apresentação (13 slides). Cópia de `Astro Apresentacao.dc.html` com nome fácil de digitar. |
| `astro-app.html` | Moldura de iPhone com o app embutido (usada pelo slide 10 "A jornada no app"). |
| `index.html` + `assets/` + `welcome/` | O **app** (build do `app/`, modo demonstração). Abre na raiz do site. |
| `_redirects` | Netlify / Cloudflare Pages: qualquer rota do app (`/inicio`, `/pix`…) devolve o `index.html`. |
| `vercel.json` | O mesmo para a Vercel. |
| `servir.py` | Servidor local (`py servir.py` → http://localhost:8777). Só para testar no PC. |

Endereços depois de publicado:
- **Apresentação (notebook):** `https://SEU-SITE/apresentacao.html` → slide 10 tem o app interativo.
- **App em tela cheia (celular):** `https://SEU-SITE/`

## 2. Como o Pix funciona entre aparelhos (importante entender)

O app está em **modo demonstração** (sem backend). Os dados (pessoas, contas,
saldos, chaves Pix, transações) ficam no `localStorage` (`astro-demo-banco`) **e são
espelhados num JSON público compartilhado**:

```
https://api.npoint.io/a325ee4d79ee921e8075
```

- Esse endereço foi embutido no build pela variável `VITE_DEMO_SYNC_URL`
  (ver `app/src/mocks/banco.ts`: `puxar()` antes de ler, `salvar()` → envia depois de mudar).
- Por isso **todo aparelho que abrir o site enxerga as mesmas contas**: uma chave criada
  no notebook é encontrada no celular, e o Pix aparece no saldo/extrato de quem recebe.
- Senhas de contas novas vão como hash SHA-256; ainda assim o JSON é público para quem
  tiver o link → **usar só dados fictícios**.
- E-mail desconhecido no login entra na conta de exemplo (Marina / Rodoforte) — é o
  roteiro da apresentação. Conta criada entra com o próprio e-mail e senha.
- Limitação conhecida: duas operações no mesmo segundo em aparelhos diferentes → vale
  a última. No ritmo de uma apresentação não acontece.

Testado (2026-10-08) com dois navegadores isolados: notebook (app no slide) cadastrou
chave de e-mail → celular achou a chave e mandou R$ 42 → notebook recebeu (saldo e
extrato "Pix de …").

## 3. Publicar (escolha UM — todos grátis, sem instalar nada no PC)

O que publicar é **o conteúdo da pasta `apresentacao/`** (a raiz do site é ela).

> ⚠️ **A raiz do site TEM que ser a pasta `apresentacao/`.** O app usa caminhos
> absolutos (`/assets/...`, `/bem-vindo`, `/inicio`). Se o site publicado for a raiz do
> repositório, o endereço vira `.../apresentacao/apresentacao.html` e o app dá 404 /
> tela branca. Teste rápido: `https://SEU-SITE/` tem que abrir o app (tela "Criar conta /
> Entrar"). Se abrir uma lista de arquivos, um 404 ou o README, a raiz está errada.
>
> No Netlify **pelo GitHub**, o `netlify.toml` da raiz do repositório já aponta para
> `apresentacao/` (não precisa configurar nada; se o painel tiver "Publish directory"
> preenchido com outra coisa, apague).
>
> Pelo mesmo motivo, **localmente use só `py servir.py`** dentro de `apresentacao/`.
> Abrir o `.html` com duplo clique, Live Server ou `python -m http.server` na raiz do
> repositório não funciona.

### A) Netlify — arrastar e soltar (mais rápido)
1. https://app.netlify.com/drop (entrar com conta grátis, ex.: login do GitHub).
2. Arrastar a pasta `apresentacao/` inteira. Pronto: aparece `https://xxxx.netlify.app`.
3. Para atualizar depois: no site → **Deploys** → arrastar a pasta de novo (o link não muda).

### B) Vercel — pelo GitHub (não usa créditos do Netlify)
1. https://vercel.com → login com GitHub → **Add New → Project** → importar
   `alefkaue/payment-platform` (quem não é dono do repo pode fazer um fork antes).
2. **Branch:** `apresentacao-interativa`. **Root Directory:** `apresentacao`.
   **Framework Preset:** Other. **Build Command:** vazio. **Output Directory:** `.` (vazio/padrão).
3. Deploy. O `vercel.json` já cuida das rotas do app.

### C) Cloudflare Pages
**Workers & Pages → Create → Pages → Upload assets** → enviar a pasta `apresentacao/`.
O `_redirects` já funciona lá.

> ⚠️ **Não** use GitHub Pages "puro": ele não reescreve rotas do SPA e as telas do app
> dão 404 ao recarregar.

Depois de publicar: abrir o link nos dois aparelhos e **recarregar** (ou aba anônima)
para não pegar versão antiga do cache.

## 4. Conferir que está certo (2 minutos)

1. Notebook: `https://SEU-SITE/apresentacao.html` → ir ao slide 10 → o app aparece no celular desenhado.
   No app do slide: **Entrar** com qualquer e-mail e senha → cai na conta de exemplo (Marina).
2. Celular: `https://SEU-SITE/` → **Criar conta** (dados fictícios, CPF válido, ex.: 111.444.777-35)
   → **Iniciar verificação**. Se a câmera não ajudar, depois de 8 s aparece
   **Continuar sem câmera (demonstração)**. → **Criar conta** → **Depositar** R$ 100.
3. Celular: **Transferir** → chave `marina@email.com` → valor → **Revisar** → **Confirmar**.
4. Notebook (app do slide): **Extrato** (menu "Mais") → aparece "Pix de …".

A conta de exemplo e as chaves dela (`marina@email.com`) existem sempre: o app as recria
se o JSON compartilhado estiver sem elas. O caminho inverso também funciona (notebook
cria uma chave em **Pix → Minhas chaves** e o celular manda para ela).

Se o passo 4 der "Chave Pix ou conta não encontrada": o site publicado é um build
**sem** `VITE_DEMO_SYNC_URL` (antigo). Conferir com:
`grep -l a325ee4d79ee921e8075 apresentacao/assets/*.js` → tem que achar um arquivo `api-*.js`.

## 5. Se precisar mudar o app e refazer o build

Node 18+ (no PC sem admin: Node portátil em zip do nodejs.org, ver `HANDOFF.md` §3).

```bash
cd app
echo "VITE_DEMO_SYNC_URL=https://api.npoint.io/a325ee4d79ee921e8075" > .env
npm ci
npm run build
node scripts/assemble-www.mjs          # gera app/www/
cd ..
rm -rf apresentacao/assets apresentacao/welcome
cp -r app/www/assets apresentacao/assets
cp -r app/www/welcome apresentacao/welcome
cp app/www/index.html apresentacao/index.html
```

Não apague `apresentacao/_redirects`, `vercel.json`, `astro-app.html`, `apresentacao.html`.
Testes do app: `cd app && npx vitest run` (inclui `src/lib/demo.test.ts`: cadastro,
chaves, Pix entre contas).

Para "zerar" os dados compartilhados (ex.: antes da banca): pedir ao usuário — é um
POST de `{}` no endereço do npoint; o app recria a conta de exemplo sozinho.

## 6. Alternativa com backend de verdade (opcional, mais lenta)

A branch `main` tem `Dockerfile` + `render.yaml` para subir o backend FastAPI de
demonstração no Render (grátis) — ver `HANDOFF.md` §12. Aí o build do app usa
`VITE_API_URL=<url do Render>` em vez de `VITE_DEMO_SYNC_URL`. Só vale a pena se
precisarem de regras completas do backend; para a apresentação, o modo acima basta.
