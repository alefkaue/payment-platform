# PayFlow - MVP (v4)

MVP sem banco de dados (dados em memória), para entrega rápida.
Estrutura já organizada para facilitar a migração futura para Azure.

## O que mudou na v4: MFA por biometria facial (real, não mais TODO)

Cadastro e transferência agora exigem uma foto do rosto. Implementado com
[DeepFace](https://github.com/serengil/deepface):

- **Cadastro** (`POST /usuarios`): a foto passa por **liveness detection**
  (anti-spoofing — rejeita foto de foto/tela) e vira um **embedding facial**
  (vetor, ~128 números) guardado junto da carteira. A foto em si nunca é
  armazenada — só esse vetor, separado dos dados da conta no repositório.
- **Transferência** (`POST /pagamentos/transferir`): exige uma nova foto ao vivo.
  Ela passa pelo mesmo liveness e depois é comparada (`distância` de cosseno)
  com o embedding cadastrado na carteira de **origem**. Só autoriza o débito se
  bater. A resposta devolve um bloco `verificacao_facial` com distância, limite
  e confiança, pra dar transparência de que a checagem rodou de verdade.

Por que só o DeepFace (dos 5 links que você mandou): os dois projetos de
"Face Recognition Authentication/System" são, eles mesmos, exemplos construídos
em cima do DeepFace (ou de lib equivalente); o "Face-Liveness-Detection" e o
`liveness-detector` resolveriam só a parte de liveness, exigindo uma segunda lib
por cima para o reconhecimento em si. O DeepFace entrega liveness (anti-spoofing)
e reconhecimento facial no mesmo lugar — 1 dependência para uma plataforma de
pagamento, não um banco.

**Limitação real, testada, não teórica:** liveness passiva (1 foto, sem vídeo/desafio)
não é perfeita. Em teste local, uma foto legítima da mesma pessoa foi rejeitada como
"spoof" (score bem na fronteira do limiar) enquanto outras duas fotos da mesma pessoa
passaram sem problema. Em uso real, com foto tirada na hora pela câmera (não uma
imagem baixada), a taxa de falso-rejeite tende a ser menor — é para isso que o modelo
foi treinado — mas não é zero. Trate um 401 de liveness como "peça para tirar outra
foto", não como bug. Se isso incomodar na demo, é um ponto justo para citar como
próximo passo (liveness ativa por vídeo/desafio, exatamente o que os outros dois
projetos que você mandou fariam, com mais fricção de UX em troca de mais robustez).

### Detalhes técnicos assumidos (documentados também em `biometria_service.py`)

- `model_name="Facenet"` (128-d, ~92MB, roda bem em CPU). Trocar para "Facenet512"
  ou "ArcFace" para mais acurácia (mais lento); "SFace"/"GhostFaceNet" para menos
  latência.
- `detector_backend="opencv"` (mais rápido, já vem com o opencv-python, sem
  download extra). Menos robusto a ângulo/iluminação ruim que "retinaface"/"mtcnn".
- **Latência real medida**: ~3-6s por chamada em CPU (cadastro faz 1 chamada de
  liveness + 1 de embedding; transferência faz as mesmas 2 na foto nova). O front
  desabilita o botão e mostra "Verificando rosto..." enquanto isso roda — não é
  travamento.
- **Primeira chamada é mais lenta** (~15s no teste local): o DeepFace baixa os
  pesos dos modelos (Facenet + anti-spoofing, ~100MB, de
  `github.com/serengil/deepface_models`) e guarda em `~/.deepface`. Da segunda
  chamada em diante, só o tempo de inferência normal.

## Como rodar localmente (sem Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> A instalação agora inclui `deepface` + `tensorflow` + `tf-keras` — é bem mais
> pesada que antes (alguns minutos, ~1-2GB). E a **primeira** requisição de
> `/usuarios` ou `/pagamentos/transferir` precisa de internet para baixar os
> pesos dos modelos (ver acima). Depois disso funciona offline.

A API sobe em http://127.0.0.1:8000
Documentação automática (Swagger): http://127.0.0.1:8000/docs

Depois, abra `frontend/index.html` direto no navegador (duplo clique). No
celular, o campo de foto abre a câmera frontal direto (`capture="user"`); no
desktop, abre o seletor de arquivo — tire a foto com o app de câmera do sistema
e selecione o arquivo.

## Como rodar em Ubuntu Server sem Docker

Ver o tutorial completo que passei antes (venv + `uvicorn --host 0.0.0.0` +
liberar porta no `ufw` + servir o `frontend/` com `python -m http.server` se for
acessar de outra máquina). Continua valendo igual — nada mudou nesse fluxo,
só o `pip install` ficou mais demorado por causa do DeepFace/TensorFlow.

## Roteiro de teste (fluxo livre + MFA)

1. Abra `frontend/index.html`.
2. Em **Criar Conta**: `Nome: Alef` / `ID: 101` / `Saldo: 500` + uma foto do seu
   rosto -> **Criar**. Espere alguns segundos (mais na primeira vez).
3. Repita simulando outra pessoa: `Nome: Bianca` / `ID: 202` / `Saldo: 50` + uma
   foto (pode ser sua mesmo, ou de outra pessoa/foto na tela para testar o
   liveness) -> **Criar**.
4. Em **Transferir**: `Meu ID: 101` / `Destino: 202` / `Valor: 100` + uma **nova**
   foto sua -> **Transferir**. Se a foto bater com a da conta 101, autoriza.
5. Teste o bloqueio: tente transferir da conta 101 usando a foto de outra pessoa
   (ou uma foto antiga da conta 202) -> deve voltar 401 "rosto não corresponde".
6. Confira os saldos em http://127.0.0.1:8000/usuarios.

Casos de erro já tratados: ID de carteira duplicado (409, falha antes de processar
a foto), carteira de origem/destino inexistente (404), rosto não corresponde (401),
liveness falhou -- foto de foto/tela (401), nenhum ou mais de 1 rosto na foto (400),
saldo insuficiente (400), valor <= 0 (400/422), transferência para si mesmo (400).

> Atenção: os dados (incluindo os embeddings faciais) vivem na memória do processo.
> Reiniciar o `uvicorn` zera tudo -- inclusive as biometrias cadastradas.

## Como rodar com Docker

```bash
docker compose up --build
```

O `Dockerfile` já instala `libgl1` e `libglib2.0-0`, que o `opencv-python` (usado
pelo DeepFace) precisa e a imagem `python:3.12-slim` não traz por padrão -- sem
isso o container derruba com `ImportError: libGL.so.1` na primeira foto processada.
Tem também um passo opcional comentado no Dockerfile para baixar os pesos do
modelo durante o build (deixa o container pronto para uso offline).

## Estrutura

```
backend/
  app/
    main.py                     # cria o app FastAPI ("PayFlow"), CORS (sem seed)
    repositories/
      memoria_repository.py     # "banco" em memória: contas por carteira_id +
                                 # embeddings faciais num dict separado
    schemas/
      usuario.py                # UsuarioCreate: nome, carteira_id, saldo_inicial,
                                 # foto_rosto_base64
      transacao.py              # TransacaoCreate: + foto_verificacao_base64
                                 # TransacaoResponse: + verificacao_facial
    services/
      usuario_service.py        # cria conta: valida ID duplicado, cadastra biometria
      pagamento_service.py      # transfere: valida saldo/IDs, MFA facial, debita/credita
      biometria_service.py      # liveness + embedding + comparação (DeepFace)
    routers/
      usuarios.py               # GET/POST /usuarios, GET /usuarios/{carteira_id}
      pagamentos.py              # POST /pagamentos/transferir, GET /pagamentos/transacoes
  Dockerfile                    # + libgl1/libglib2.0-0 para o opencv
  requirements.txt              # + deepface, tf-keras, opencv-python, numpy
docker-compose.yml
frontend/
  index.html                    # Seção 1: Criar Conta (+ foto) | Seção 2: Transferir (+ foto)
```

## Ganchos que ainda são só TODO (não implementados agora)

Para localizar: `grep -rn "TODO\[" backend/`

| Gancho | Arquivo | Onde |
|---|---|---|
| Split Payment (CNPJ) | `services/pagamento_service.py` | Antes do débito/crédito |
| Azure (Cosmos DB / SQL) | `usuario_service.py`, `pagamento_service.py`, `memoria_repository.py` | Troca da implementação do repositório |

Liveness Detection, Reconhecimento Facial e MFA **saíram da lista** -- viraram
código de verdade em `biometria_service.py`, testado com fotos reais.

## O que falta para virar produto real (pós-entrega)

- Trocar `MemoriaRepository` por um repositório ligado a Azure SQL Database ou
  Azure Cosmos DB. O embedding facial deveria ir para um datastore separado dos
  dados da conta (a divisão já existe no repositório em memória), com o vetor
  criptografado em repouso -- é **dado biométrico, "dado sensível" pela LGPD**
  (art. 5º, XIII), então isso pede consentimento explícito, política de retenção
  e cuidado redobrado se isso sair do MVP.
- **Login/sessão — ainda não existe.** O MFA facial autoriza a *transferência*,
  mas qualquer um ainda pode chamar `GET /usuarios/{id}` ou criar contas em nome
  de qualquer `carteira_id` livre. Não há conceito de "sessão autenticada".
- Liveness passiva por foto única tem falso-rejeite (ver limitação documentada
  acima). Para produção, considerar liveness ativa (desafio/vídeo) para reduzir
  isso, ou permitir "tentar de novo" de forma clara no front (já dá pra tentar
  de novo hoje, só recarregando a foto).
- Idempotência nas transferências (hoje um double-click gera duas transações
  *e* cobra o MFA duas vezes).
- Trocar `float` por `Decimal` ou centavos inteiros para valores monetários.
- Restringir `allow_origins` do CORS ao domínio do front publicado.
- Deploy do backend em Azure Container Apps ou App Service (Dockerfile pronto).
- Deploy do frontend em Azure Static Web Apps.
- Segredos via Azure Key Vault.
- Latência de ~3-6s por chamada facial é síncrona (bloqueia o request). Para
  volume real, pediria fila/processamento assíncrono.

## Endpoints

- `POST /usuarios` — `{ "nome": "Alef", "carteira_id": 101, "saldo_inicial": 500.0, "foto_rosto_base64": "data:image/jpeg;base64,..." }` -> 201
- `GET /usuarios` — lista carteiras e saldos (sem nenhum dado biométrico)
- `GET /usuarios/{carteira_id}` — consulta uma carteira
- `POST /pagamentos/transferir` — `{ "origem_carteira_id": 101, "destino_carteira_id": 202, "valor": 100.0, "foto_verificacao_base64": "data:image/jpeg;base64,..." }` -> inclui `verificacao_facial` na resposta
- `GET /pagamentos/transacoes` — histórico de transações, cada uma com `verificacao_facial`
