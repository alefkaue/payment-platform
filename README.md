# PayFlow - MVP (v5)

Backend organizado para rodar de dois jeitos, escolhido só por uma variável de
ambiente, sem trocar nenhum código:
- **Sem `DATABASE_URL` configurada**: repositório em memória (como nas versões
  anteriores) -- bom pra um teste rápido sem precisar subir banco nenhum.
- **Com `DATABASE_URL` configurada**: Postgres de verdade, com as 8 tabelas do
  DER que vocês definiram, criadas automaticamente no primeiro boot.

## O que mudou na v5: persistência em PostgreSQL (DER completo)

Implementei as 8 entidades do DER: `Usuarios/Empresas`, `Carteiras`,
`Transacoes`, `Sessoes/MFA`, `Historico`, `Logs_Auditoria`, `Split_Regras`,
`Split_Liquidacao` (nomes de tabela em `app/db/models.py`: `usuarios`,
`carteiras`, `transacoes`, `sessoes_mfa`, `historico_saldo`, `logs_auditoria`,
`split_regras`, `split_liquidacoes`).

**Não tenho o diagrama DER de vocês, só os nomes das entidades** -- modelei os
campos com base em tudo que já construímos + no que cada nome sugere. Onde
assumi algo que pode divergir do diagrama de vocês, tem um comentário
`ASSUNCAO` no topo de `app/db/models.py`. Os pontos mais prováveis de
divergir:
- `Historico` virou um livro-razão de saldo (saldo antes/depois a cada
  transação) -- se no DER de vocês for outra coisa (histórico de login,
  de dispositivo, etc.), é só eu remodelar.
- `Usuarios/Empresas` virou 1 tabela com campo `tipo` (PF/PJ), não 2 tabelas.
- `Split_Regras`/`Split_Liquidacao`: schema pronto, mas a LÓGICA do motor de
  split ainda não está implementada -- fica pro próximo passo (Loja/Viagens).

### Dois bugs que fechei aproveitando que já estava mexendo nisso

1. **Dinheiro agora é `Numeric`, não `float`, em todas as colunas de valor.**
   Já tinha sinalizado isso antes como problema (float perde precisão em
   centavos) -- resolvido na migração.
2. **Condição de corrida na transferência, fechada e testada de verdade.**
   Também já tinha sinalizado: duas transferências simultâneas da mesma
   carteira podiam as duas passar no "saldo suficiente" antes de qualquer
   uma debitar, e estourar o saldo. Testei com 5 requisições disparadas ao
   mesmo tempo numa carteira com saldo pra exatamente 4 -- resultado: 4
   sucessos, 1 falha limpa de "saldo insuficiente", saldo final bateu exato
   (sem overdraft). No Postgres isso é `SELECT ... FOR UPDATE` (trava as
   linhas até o commit); no repositório em memória é um `threading.Lock`.
   Os dois protegem a mesma coisa, dá pra usar qualquer um com confiança.

### O que NÃO fiz nesta rodada (de propósito, escopo já estava grande)

- **Motor de Split Payment**: as tabelas existem, o cálculo não. Combina com
  a Loja/Viagens que vocês querem fazer depois.
- **Deploy na Azure VM**: o schema/app já está pronto pra apontar pra
  qualquer Postgres (local, Azure Database for PostgreSQL, RDS, o que for) --
  só troca a `DATABASE_URL`. Mas eu não configurei a VM em si, isso depende
  de vocês terem a assinatura Azure em mãos.
- **3º container (biometria separada)**: fiquei em 2 containers (`backend` +
  `db`). Separar a biometria em outro serviço significa o container da API
  chamar outro container por HTTP toda vez que precisar verificar um rosto --
  mais latência de rede, mais complexidade de deploy, sem um ganho claro
  agora (não tem necessidade de escalar isso independente ainda). Fica fácil
  de fazer depois se aparecer uma razão concreta (ex: rodar o DeepFace numa
  máquina com GPU separada da API).
- **Alembic** (migrações versionadas): hoje o schema é criado com
  `Base.metadata.create_all()` no boot -- perfeito pra criar as tabelas do
  zero, mas não sabe fazer `ALTER TABLE` em cima de dados que já existem.
  Enquanto for só desenvolvimento, sem dado real pra perder, isso é
  suficiente. No dia que o schema mudar com dado de produção já dentro,
  Alembic vira necessário -- não é grande de adicionar depois.
- **JWT / sessão de login**: a tabela `sessoes_mfa` existe e registra cada
  tentativa de biometria (sucesso ou falha), mas isso não é a mesma coisa que
  autenticação de usuário (login com senha, token JWT, `GET /usuarios/{id}`
  protegido). Esse é o "Fluxo de autenticação" que está nos diagramas C4 de
  vocês como componente separado do Core de Pagamentos -- ainda não construído.

## Como rodar localmente

### Opção A -- sem Postgres (mais rápido pra testar algo pontual)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Sem `DATABASE_URL` no ambiente, cai automaticamente no repositório em
memória -- reiniciar o `uvicorn` zera tudo, igual antes.

### Opção B -- com Postgres (recomendado a partir de agora)

```bash
sudo apt install -y postgresql
sudo -u postgres psql -c "CREATE USER payflow WITH PASSWORD 'payflow';"
sudo -u postgres psql -c "CREATE DATABASE payflow OWNER payflow;"

cd backend
cp ../.env.example .env
# .env já vem com DATABASE_URL=postgresql+psycopg2://payflow:payflow@localhost:5432/payflow
# ajuste usuário/senha/host se for diferente

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
set -a; source .env; set +a     # carrega o .env nesta sessão do shell
uvicorn app.main:app --reload
```

No log de boot, confirme `INFO: Application startup complete.` sem erro de
conexão -- as 8 tabelas são criadas automaticamente na primeira subida.
`curl http://127.0.0.1:8000/` deve responder com `"repositorio": "postgres"`
(se vier `"memoria"`, o `.env` não foi carregado nessa sessão do shell).

> A instalação inclui `deepface` + `tensorflow` + `tf-keras` -- pesada
> (alguns minutos, ~1-2GB), e a **primeira** requisição com foto baixa os
> pesos dos modelos (precisa de internet nessa hora, depois funciona offline).
> `opencv-python` precisa de `libgl1`/`libglib2.0-0` no sistema (Ubuntu
> Server não traz por padrão): `sudo apt install -y libgl1 libglib2.0-0`.
> E o pacote tem que ser só `opencv-python` -- nada de instalar também
> `opencv-python-headless` ou `opencv-contrib-python` junto, os três
> conflitam entre si e corrompem o `cv2/data/` (foi exatamente isso que
> aconteceu na v4).

A API sobe em http://127.0.0.1:8000 -- Swagger em http://127.0.0.1:8000/docs

Depois, abra `frontend/index.html` direto no navegador (duplo clique). No
celular, o campo de foto abre a câmera frontal (`capture="user"`); no
desktop, abre o seletor de arquivo.

## Como rodar em Ubuntu Server sem Docker

Mesmo tutorial de sempre (venv + `uvicorn --host 0.0.0.0` + `ufw allow` +
servir o `frontend/` com `python -m http.server` se for acessar de outra
máquina). Se for usar Postgres, ele só precisa estar acessível pelo host que
roda a API -- rodando local na mesma VM funciona igual ao exemplo acima.

## Como rodar com Docker

```bash
docker compose up --build
```

Agora são 2 containers: `backend` (API) e `db` (Postgres 16, com volume
nomeado `payflow_db_data` -- sobrevive a `docker compose down`, só some com
`docker compose down -v`). O `backend` já sobe apontando `DATABASE_URL` pro
serviço `db` pelo nome (`db:5432`, resolvido pela rede interna do Compose).
Pra rodar em memória mesmo dentro do Docker, comente a linha `DATABASE_URL`
do serviço `backend` no `docker-compose.yml`.

## Roteiro de teste (fluxo livre + MFA)

1. Abra `frontend/index.html`.
2. Em **Criar Conta**: `Nome: Alef` / `ID: 101` / `Saldo: 500` + uma foto do
   rosto -> **Criar**.
3. Repita simulando outra pessoa: `Nome: Bianca` / `ID: 202` / `Saldo: 50` +
   uma foto -> **Criar**.
4. Em **Transferir**: `Meu ID: 101` / `Destino: 202` / `Valor: 100` + uma
   **nova** foto sua -> **Transferir**.
5. Teste o bloqueio: tente de novo com a foto de outra pessoa -> 401.
6. Se estiver com Postgres, dá pra inspecionar direto:
   `sudo -u postgres psql -d payflow -c "SELECT * FROM carteiras;"`.

Casos de erro já tratados: ID de carteira duplicado (409), carteira de
origem/destino inexistente (404), rosto não corresponde (401), liveness
falhou (401), nenhum ou mais de 1 rosto na foto (400), saldo insuficiente
(400), valor <= 0 (400/422), transferência para si mesmo (400).

## Estrutura

```
backend/
  app/
    main.py                       # FastAPI ("PayFlow"), CORS, cria tabelas no boot
    db/
      base.py                     # engine/sessão SQLAlchemy via DATABASE_URL
      models.py                   # as 8 tabelas do DER
    repositories/
      __init__.py                 # escolhe MemoriaRepository x PostgresRepository
      memoria_repository.py       # repositório em memória, com lock
      postgres_repository.py      # repositório Postgres, com SELECT...FOR UPDATE
      exceptions.py                # SaldoInsuficienteError (comum aos dois repos)
    schemas/
      usuario.py                  # UsuarioCreate: + foto_rosto_base64
      transacao.py                # TransacaoCreate: + foto_verificacao_base64
    services/
      usuario_service.py          # cria conta: ID duplicado, cadastra biometria
      pagamento_service.py        # transfere: valida IDs, MFA facial, chama repo
      biometria_service.py        # liveness + embedding + comparação (DeepFace)
    routers/
      usuarios.py
      pagamentos.py
  Dockerfile
  requirements.txt                # + sqlalchemy, psycopg2-binary, python-dotenv
.env.example                      # template de DATABASE_URL
docker-compose.yml                # backend + db (Postgres 16)
frontend/
  index.html
```

## Ganchos que ainda são só TODO

Para localizar: `grep -rn "TODO\[" backend/`

| Gancho | Arquivo | Onde |
|---|---|---|
| Split Payment (CNPJ) | `services/pagamento_service.py` | Antes do débito/crédito |
| Idempotência (double-click) | `services/pagamento_service.py` | Ao redor de `executar_transferencia` |
| Atomicidade cadastro+biometria | `services/usuario_service.py` | 2 escritas separadas no Postgres |

Liveness, Reconhecimento Facial, MFA, persistência do DER e a condição de
corrida na transferência **saíram da lista** -- código de verdade, testado.

## O que falta para virar produto real

- **Login/sessão -- ainda não existe.** O MFA facial autoriza a
  *transferência*, mas `GET /usuarios/{id}` e a criação de conta continuam
  sem autenticação nenhuma.
- Motor de Split Payment (schema pronto, cálculo não).
- Deploy de verdade numa VM Azure (o app já é agnóstico de onde o Postgres
  está rodando).
- Alembic para migrações versionadas (ver nota acima).
- Restringir `allow_origins` do CORS ao domínio do front publicado.
- Segredos (senha do banco, etc.) via Azure Key Vault em vez de `.env`.
- Latência de ~3-6s por chamada facial é síncrona. Pra volume real, filas
  ou processamento assíncrono.
- Liveness passiva tem falso-rejeite conhecido (documentado desde a v4) --
  considerar liveness ativa (vídeo/desafio) se isso incomodar na prática.

## Endpoints

- `POST /usuarios` — `{ "nome": "Alef", "carteira_id": 101, "saldo_inicial": 500.0, "foto_rosto_base64": "..." }` -> 201
- `GET /usuarios` — lista carteiras e saldos (sem dado biométrico)
- `GET /usuarios/{carteira_id}` — consulta uma carteira
- `POST /pagamentos/transferir` — `{ "origem_carteira_id": 101, "destino_carteira_id": 202, "valor": 100.0, "foto_verificacao_base64": "..." }` -> inclui `verificacao_facial`
- `GET /pagamentos/transacoes` — histórico
- `GET /` — `{"status": "ok", "servico": "payflow", "repositorio": "postgres"|"memoria"}` -- útil pra confirmar qual modo está ativo
