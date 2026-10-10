# Astro — como o dono sobe o ambiente local do pentest

Este guia é para o **dono do PC servidor**. Os grupos entram pelo web em
`<URL_WEB>`; o APK debug em emulador é um alvo extra. Regras em `PENTEST.md`.

A API roda no PC do dono, com SQLite, exposta por um túnel cloudflared HTTPS.
Outro túnel serve o app web. O túnel não expõe o IP do dono e não exige abrir
porta no roteador. O PC e os quatro processos (API, servidor web e dois túneis)
precisam permanecer ligados. As URLs mudam a cada reinício dos túneis.

Azure continua como destino final (`AZURE.md`), ainda não publicado. Este guia usa
o checkout atual, sem branch de apresentação nem pasta `apresentacao`.

## 1. Preparar ferramentas

- Python 3.12 e dependências de `backend/requirements.txt`.
- Node compatível com o Vite/Capacitor do projeto e npm; use o lockfile com `npm ci`.
- cloudflared instalado e disponível no terminal.
- Para APK: Android Studio, SDK Android e **JDK 21**. O JBR do Android Studio novo
  é Java 25 e quebra o Gradle 8.14 usado pelo projeto. Configure `JAVA_HOME` e o
  Gradle JDK para o JDK 21; confira com `java -version` e `gradlew.bat --version`.

Os comandos abaixo são para PowerShell, a partir da raiz do projeto. Não publique
segredos, banco, documentos ou arquivos `.env`.

## 2. Backend e configuração de pentest

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Prepare `backend/.env` em UTF-8 sem BOM. Substitua os marcadores por valores próprios;
não use os marcadores de segredo como valores literais.

```dotenv
AMBIENTE=desenvolvimento
JWT_SECRET=<SEGREDO_ALEATORIO>
EMBEDDING_KEY=<CHAVE_FERNET>
ADMIN_EMAIL=<EMAIL_ADMIN>
ADMIN_SENHA=<SENHA_ADMIN_FORTE>
ADMIN_IPS_PERMITIDOS=127.0.0.1
ATESTACAO_EXIGIDA=0
CNPJ_PROVEDOR=stub
DEPOSITO_DEMO=1
DPOP_OBRIGATORIO=1
BIOMETRIA_MOTOR=opencv
CORS_ORIGINS=<URL_WEB>,https://localhost
```

Sem `DATABASE_URL`, desenvolvimento usa SQLite local. Preserve banco e chaves entre
reinícios. Gere as chaves localmente:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Não habilite BIOMETRIA_STUB nem BIOMETRIA_STUB_CADASTRO.** Remova valores antigos
dessas variáveis no arquivo e no ambiente do processo: o padrão é biometria real.
STUB aprova qualquer rosto e serve apenas para demo; não é o perfil do pentest.
O motor padrão é OpenCV, sem precisar instalar DeepFace/TensorFlow por fora.

Baixe e confira os modelos antes de abrir o teste:

```powershell
.\.venv\Scripts\python.exe -m app.core.modelos baixar
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Confirme que todos os modelos, inclusive MiniFASNet, foram obtidos e carregam.
Em desenvolvimento, a ausência do modelo passivo pode apenas gerar aviso e
desligar essa camada; instalar as bibliotecas não comprova anti-spoofing ativo.
Para leitura automática dos documentos, confira Tesseract e idioma português:
`DOCUMENTO_PROVEDOR=auto` usa `sem_ocr` se o binário não estiver disponível, deixando
o texto para análise. Não use stub de documento como se fosse validação real.

`GET /` deve responder:

```json
{"status":"ok","servico":"astro","versao":"9.0"}
```

## 3. Abrir os dois túneis

Em outro terminal, abra o túnel da API:

```powershell
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
```

Anote a URL HTTPS impressa como `<URL_API>`. Abra mais um terminal para o túnel web
(o servidor local será preparado na seção 5):

```powershell
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8777
```

Anote essa URL como `<URL_WEB>`. Atualize `CORS_ORIGINS` no backend com **a origem
exata do web**, sem caminho ou barra final, e `https://localhost` (origem do APK).
Reinicie a API após alterar o `.env`. Não use curinga.

O Uvicorn restaura o IP encaminhado apenas do conector local confiável. Mantenha
a API ligada ao loopback e não use confiança em todos os proxies. Confira com
duas redes externas que a API identifica os visitantes e **recusa login/rotas admin
pelo túnel**. A lista administrativa permite somente `127.0.0.1`; não desligue os
proxy headers, pois isso pode fazer um visitante remoto parecer o conector local.

## 4. Compilar web e APK para a mesma API

Em outro terminal, na raiz do projeto:

```powershell
cd app
$env:VITE_API_URL="<URL_API>"
npm ci
npm run build:mobile
```

O comando compila o web, gera os cabeçalhos, monta `app/www` e sincroniza o Android.
`VITE_API_URL` entra no bundle e na CSP durante o build; não basta mudar o backend
depois. Sem API configurada, o app pode entrar em modo demonstração.

Para gerar o APK debug local, com `JAVA_HOME` já apontando ao JDK 21:

```powershell
cd android
.\gradlew.bat --version
.\gradlew.bat assembleDebug
```

O arquivo fica em `app/android/app/build/outputs/apk/debug/app-debug.apk`. Entregue
esse APK aos grupos. Se a instalação retornar `INSTALL_FAILED_VERSION_DOWNGRADE`,
desinstale a versão anterior antes de instalar (apaga os dados locais).

**Pinning só no APK do CI com a URL fixa da API** (`ASTRO_API_URL`): o CI executa
`scripts/pinos.mjs`. O APK local do túnel usa o XML base, apenas CAs do sistema,
sem CA de usuário. Não gere pinos para uma URL temporária. Confira que o checkout
local usa esse XML base antes de compilar.

## 5. Servir o web com os cabeçalhos

Sirva **`app/www`** em `127.0.0.1:8777`, com um servidor estático configurado para:

- Aplicar efetivamente os cabeçalhos de `www/_headers` a todas as respostas,
  incluindo `index.html`, assets e fallback.
- Usar `index.html` como fallback das rotas do app, preservando assets reais.
- Servir os tipos corretos (inclusive WASM) e evitar cache antigo do HTML/CSP.

`_headers` é configuração de host, não um mecanismo executado pelo navegador.
Um servidor genérico, como `python -m http.server` ou `http-server`, não aplica
essa política só porque o arquivo existe. cloudflared fornece o túnel HTTPS,
mas não transforma esse arquivo em cabeçalhos de resposta.

A política gerada inclui CSP com hashes dos scripts e `connect-src` para
`<URL_API>`, `X-Frame-Options`, `nosniff`, HSTS, política de referência,
`Cross-Origin-Opener-Policy` e `Permissions-Policy` com `camera=(self)`.
Preserve também as origens do WASM/modelo MediaPipe previstas no build.
Não remova a CSP para contornar erro de configuração.

## 6. Conferir antes de entregar

| Conferência | Resultado esperado |
|---|---|
| API pública, `GET /` | JSON da seção 2 |
| Web por `<URL_WEB>` | Cabeçalhos presentes nas respostas e câmera permitida |
| Cadastro/login web e APK | Mesma API, facial real, sem demo |
| Admin pelo túnel | Recusado; acesso só local autorizado |
| Emulador | Sem nível de atestação, aceito com `ATESTACAO_EXIGIDA=0` |
| Saldo de teste | Depósito próprio até R$ 10.000 por chamada |

As decisões do grupo valem neste ambiente: KYC pendente movimenta em desenvolvimento
(em produção não), rosto × documento é informativo, CNPJ/quadro societário é stub e
gerar saldo próprio é permitido. Um documento por conta, um rosto por conta e CPF
único continuam valendo.

Se reiniciar o túnel da **API**, atualize `VITE_API_URL`, refaça build e APK e
publique os novos arquivos/cabeçalhos. Se reiniciar o túnel **web**, atualize CORS
e reinicie a API; a nova origem exige novo login no navegador. Distribua os links
atuais e o APK correspondente. Não considere builds, túneis ou acesso remoto
validados apenas pela leitura deste guia.
