# Para o time — como rodar e o que mudou

Resumo rápido do que foi preparado pra facilitar a vida de todo mundo (rodar o projeto, apresentar e
preparar o pentest). Qualquer dúvida, só chamar.

## 1. Rodar o projeto inteiro em 2 comandos
Precisa só do **Docker** instalado. Não precisa de Node, Python, nem conta no Docker Hub.

```bash
git clone https://github.com/alefkaue/payment-platform
cd payment-platform
./install.sh      # checa o Docker, gera os segredos de teste e baixa as imagens
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

## 3. Observação importante sobre o front (modo de rodar)
O stack local roda o front em **modo desenvolvimento** apontando para `http://localhost:8000`, porque o
**modo produção do app exige HTTPS** (trava de segurança do próprio `vite.config`) — e não dá HTTPS em
`localhost` puro. É normal e esperado.

- Para o **deploy real** (VPC/Azure com HTTPS), buildar o front em produção:
  `docker build --build-arg VITE_MODE=production --build-arg VITE_API_URL=https://<url-da-api> ...`
- Login/cadastro usam **biometria em stub** (aprova qualquer rosto) e há **depósito de teste** pra gerar
  saldo — tudo é **simulação**, nada é dinheiro real.

## 4. Arquitetura pra nuvem (Azure)
Dois diagramas em `docs/arquitetura/` (abrir em https://excalidraw.com — arraste o arquivo):
- **`azure-base.excalidraw`** — o desenho simples: Container Apps + Postgres + Key Vault + ACR/Docker Hub.
- **`azure-endurecida.excalidraw`** — a versão com **defesa em camadas**: Front Door + WAF na frente,
  Container Apps **privado** dentro da VNet, Postgres e Key Vault por **Private Endpoint**.

Guia técnico de deploy já existe em [`docs/operacao/AZURE.md`](operacao/AZURE.md) e o `infra/azure/main.bicep`.

> Dica pro pentest: se usarem o WAF, deixem em **modo detecção** (só loga, não bloqueia) durante os
> testes, pra não barrar os ataques dos outros grupos e ainda ter a visibilidade.

## 5. Auditoria de segurança (leitura recomendada)
Em [`docs/auditoria-personas/`](auditoria-personas/) tem uma auditoria read-only do projeto (15 "personas"
+ relatórios `01`–`11`). Começar pelo [`01-RESUMO-EXECUTIVO.md`](auditoria-personas/01-RESUMO-EXECUTIVO.md).

**Veredito:** o backend está bem endurecido (autorização por conta/papel, DPoP, isolamento do banco com
RLS, idempotência, maker-checker) — **nenhum P0/P1 confirmado**. Prioridades pro pentest (roadmap `08`):
1. garantir teste negativo de autorização em **toda** rota por id;
2. teste adversarial da biometria.

## 6. Onde está a documentação
A raiz do repo ficou limpa; tudo está organizado em `docs/`:
`arquitetura/` · `seguranca/` · `operacao/` · `ia/` · `historico/` · `auditoria-personas/`.
Índice completo em [`docs/README.md`](README.md).
