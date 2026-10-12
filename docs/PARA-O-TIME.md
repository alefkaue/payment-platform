# Para o time — como rodar e o que mudou

Resumo rápido do que foi preparado pra facilitar a vida de todo mundo (rodar o projeto, apresentar e
preparar o pentest). Qualquer dúvida, só chamar.

## 1. Rodar o perfil de apresentação
Precisa de Docker, Compose e OpenSSL. Não precisa de Node/Python na máquina nem conta no Docker Hub.
Este primeiro exemplo usa biometria de teste; para avaliar segurança, use o perfil local da seção 3.

```bash
git clone https://github.com/alefkaue/payment-platform
cd payment-platform
./install.sh --hub # prepara segredos e baixa as imagens de apresentação
./astro.sh up     # sobe os 3 containers
```
Depois: **app em http://localhost:8080** · **API (Swagger) em http://localhost:8000/docs**

### Painel de controle (`./astro.sh`)
Rode `./astro.sh` sozinho pra abrir o menu, ou use direto:
| Comando | O que faz |
|---|---|
| `./astro.sh up` | sobe os 3 containers (app, api, db) |
| `./astro.sh down` | para (mantém o banco) |
| `./astro.sh status` | mostra o que está rodando |
| `./astro.sh logs api` | acompanha os logs (api / app / db / migrate) |
| `./astro.sh clean` | apaga tudo, inclusive o banco |

## 2. Os 3 containers (públicos no Docker Hub)
São 3 imagens, todas **públicas** (qualquer um puxa, sem login) em `matheussousaavelino`:
- `payment-platform-app` — o front (telas), servido por nginx
- `payment-platform-api` — o backend (FastAPI)
- `payment-platform-db` — o Postgres com os papéis de privilégio mínimo

**Nenhum segredo fica dentro das imagens** — JWT, chaves de cifragem e senhas do banco vêm do arquivo
`.env.docker` (gerado pelo `./install.sh`, e ignorado pelo git). Em produção, viriam do Key Vault.

## 3. Dois perfis — e qual usar (⚠️ use o SEGURO)
Existem **dois jeitos** de rodar, com níveis de segurança diferentes. **Para qualquer coisa que valha
nota de segurança ou pro pentest, use o perfil SEGURO.** O de apresentação é só pra mostrar as telas.

### 🔒 Perfil SEGURO (recomendado) — `docker-compose.full.yml`
Controles **reais** ligados: **biometria real** (`BIOMETRIA_STUB=0`), **DPoP obrigatório**
(`DPOP_OBRIGATORIO=1`), CORS restrito, healthchecks. Builda do código local.
```bash
./install.sh --local # prepara segredos persistentes sem baixar as imagens de apresentação
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml up -d --build
```
> O login exige **rosto de verdade** (webcam) — é o comportamento real.

Neste perfil, JWT_SECRET, EMBEDDING_KEY e ADMIN_SENHA são passados explicitamente
à API pelo Compose. Não apague nem regenere essas chaves ao reiniciar: a chave
facial é necessária para ler os rostos já cadastrados. O instalador preserva
segredos existentes e importa do `.env` antigo somente esses três valores ausentes
do `.env.docker`, sem copiar senhas administrativas do banco para a API.

O depósito fictício está ligado e o documento é opcional. Cadastro e login
continuam com biometria real e DPoP obrigatório. O arquivo `.env` fica disponível
para outras opções da API; os segredos deste perfil ficam no `.env.docker`.

`./install.sh` sem argumentos também prepara o perfil local. O download de
imagens do Docker Hub ocorre apenas com `--hub`.

### 🧪 Perfil APRESENTAÇÃO (só demo) — `./astro.sh up`
Usa as imagens do Docker Hub com **`BIOMETRIA_STUB=1`** (aprova qualquer rosto) e **`DPOP_OBRIGATORIO=0`**.
Serve pra clicar nas telas rápido, mas **NÃO representa a segurança real** — não use pra avaliar segurança.

**Sobre o front:** nos dois casos ele roda em **modo desenvolvimento** apontando pra `http://localhost:8000`,
porque o **modo produção exige HTTPS** (trava do `vite.config`); o perfil local usa HTTP por padrão. Pro
**deploy real** (Azure com HTTPS), buildar em produção:
`docker build --build-arg VITE_MODE=production --build-arg VITE_API_URL=https://<url-da-api> ...`.
Tudo é **simulação** (dinheiro fictício), e há **depósito de teste** pra gerar saldo.

## 4. Arquitetura pra nuvem (Azure)
**3 diagramas** em `docs/arquitetura/` — ver o [`README`](arquitetura/README.md) de lá. Atenção ao status:
- ✅ **`azure-conforme-bicep.excalidraw`** — o que o `infra/azure/main.bicep` **realmente cria** (use como referência): **frontend no Static Web Apps**, só a **API no Container Apps**, **Front Door + WAF (Prevention)**, Postgres por **VNet integration** (sem rede pública, **não** é Private Endpoint), Key Vault por **RBAC + endpoint público**.
- 🟠 **`azure-endurecida.excalidraw`** e **`azure-base.excalidraw`** — **PROPOSTAS** (ideal/didático), não a infra atual.

Guia técnico: [`docs/operacao/AZURE.md`](operacao/AZURE.md) + `infra/azure/main.bicep`.

> **WAF e pentest (sem meio-termo errado):** o Bicep usa **Prevention** (bloqueia de verdade) — é o mais
> seguro. Um WAF em "detecção" **só loga, não protege**; não confundir as duas coisas. Se precisarem medir
> a segurança da **aplicação** sem o WAF no caminho, façam **uma rodada** assim e **outra rodada** com o
> WAF em Prevention pra validar o conjunto — não troquem pra detecção achando que é "o mesmo, só seguro".

## 5. Auditoria de segurança (leitura recomendada)
Em [`docs/auditoria-personas/`](auditoria-personas/) tem uma auditoria **read-only** do projeto
(relatórios `01`–`11`). Começar pelo [`01-RESUMO-EXECUTIVO.md`](auditoria-personas/01-RESUMO-EXECUTIVO.md).

**Veredito (com as ressalvas honestas):** o backend está bem endurecido (autorização por conta/papel, DPoP,
isolamento do banco com RLS, idempotência, maker-checker) e **nenhum P0/P1 foi confirmado** — **mas isso
NÃO quer dizer "sem vulnerabilidades"**. A auditoria foi **leitura estática de código**, sem verificação
dinâmica; as **15 "personas" são definições de agente**, não 15 auditorias concluídas (as análises
automáticas falharam por limite de uso). Prioridades reais pro pentest (roadmap `08`):
1. garantir **teste negativo de autorização** em **toda** rota por id;
2. **teste adversarial** da biometria (foto/vídeo/máscara).

## 6. Onde está a documentação
A raiz do repo ficou limpa; tudo está organizado em `docs/`:
`arquitetura/` · `seguranca/` · `operacao/` · `ia/` · `historico/` · `auditoria-personas/`.
Índice completo em [`docs/README.md`](README.md).
