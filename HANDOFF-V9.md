# HANDOFF v9 — Astro (segurança, login 2 fatores, KYC, PJ por porte)

> Documento para continuar o trabalho em outra sessão do Claude Code.
> Escrito em 09/10/2026, no meio da implementação; **atualizado no mesmo dia (2ª sessão)**.
> **Leia a seção "Estado" antes de tudo.**

## 0. Regras do dono do projeto (Alef) — seguir sempre

- **Sempre `git fetch` + `git pull` ANTES de mexer.** (Já houve trabalho feito em base velha.)
- Commit **direto na `main`** quando ele pedir para subir (é a branch principal).
- Projeto é **ASTRO** (o nome PayFlow ainda aparece em código/strings antigos).
- Produto final, não demo. Foco: **backend + segurança** (vai ter **pentest com Kali**) e deploy no **Azure**.
- App: só **web/PWA** por enquanto (sem APK/iOS nativo), mas tem que funcionar em celular e PC.
- Login = **senha + biometria (os dois)**. Biometria com prova de vida de verdade (nada de "aprova sem rosto").
- PJ: cada pessoa com **login próprio** (nunca conta compartilhada entre representante e contador). CNPJ → CPF do
  responsável → dentro do app o admin define **alçadas** de cada pessoa. Regras diferentes para **MEI, PME, Grande**.
- Pagamento de salário **só para funcionário** da empresa.
- Arquivo de referência de requisitos: `ASTRO_MELHORIAS_LOGICA_FRONT.md` (está só na máquina do Alef, **não versionado**).
- Responder em português.

## 1. Estado (honesto)

| Parte | Situação |
|---|---|
| Backend — código novo (abaixo) | **escrito**, importa e sobe |
| Backend — testes | ✅ **149 passando** (eram ~60 falhas). Helpers com senha forte e login em 2 etapas; `tests/test_v9_seguranca.py` com 32 testes novos (2FA, sessões, bloqueio de aparelho, convite por CPF, MEI/GRANDE, 2 aprovações, folha, KYC, MRZ, senha, headers). |
| Migração Alembic do esquema v9 | ✅ `f9a1b2c3d4e5` escrita e **testada em SQLite e Postgres 16** (banco vazio até o head, upgrade com dados, `alembic check` limpo, downgrade/upgrade). |
| Migração v7 no Postgres | ✅ **corrigida**: num banco vazio, `alembic upgrade head` quebrava (`type "papel_usuario" does not exist`), ver seção 7. |
| Frontend (`app/`) | 🟡 **login 2 fatores, cadastro com KYC, equipe/convites/aprovações** ligados ao v9 (e2e passou). **Faltam** telas de folha, segurança (aparelhos/sessões/atividade) e auditoria. |
| Branch `origin/fix/pj-login-facial` | ✅ mesclada localmente (`c84a553`) e reescrita por cima no login/cadastro. |
| Push para o GitHub | ⬜ **não feito**: os commits estão só no clone local (`Desktop/payment/astro`). Subir quando o Alef pedir. |
| Infra Azure / SECURITY.md / AZURE.md | ⬜ **não feitos** (pesquisa feita, ver seção 4). |

Commits desta frente: `6d225cf` (prova de vida multi-passo), `f7c573c` (WIP v9), e na 2ª sessão
`2a3be2c` (testes), `08125ed` (migração + correção v7), `c84a553` (merge), `cf8fc8e` (login/cadastro),
`2cc72a0` (equipe/convites/aprovações).

## 2. O que foi feito nesta rodada (backend)

### Autenticação (2 fatores obrigatórios)
- `app/services/auth_service.py` — reescrito.
  - `POST /auth/login {email|cpf, senha}` → para pessoas devolve `{mfa_requerido: true, mfa_token, mfa_expira_em, desafio}` (desafio modo `login` = piscar 3x). **Sem token de acesso.**
  - `POST /auth/login/mfa {mfa_token, biometria}` → rosto confere → `TokenResponse` (+ `sessao_id`).
  - `POST /auth/login/mfa/desafio {mfa_token}` → novo desafio (retry).
  - `/auth/login/biometria` (só rosto) **foi removido**.
  - Admin de operação (sem biometria) entra só com senha, mas só de IPs em `ADMIN_IPS_PERMITIDOS` (em produção, vazio = admin desligado). `deps.admin_atual` confere IP em toda chamada.
  - Rosto verificado no aparelho no login ⇒ aparelho vira **confiável** (é o cadastro do aparelho).
  - Senha: migração transparente bcrypt → Argon2id no login (`precisa_rehash`).
  - Sessões: `GET /auth/sessoes`, `DELETE /auth/sessoes/{sid}`, `POST /auth/sessoes/encerrar-outras`.
- `app/core/security.py` — reescrito: **Argon2id** (m=19456, t=2, p=1), JWT com `iss`/`aud`/`nbf`, tipo explícito no header (`at+jwt`, `rt+jwt`, `mfa+jwt`) e no payload, claims `dev` (hash do aparelho) e `sid` (sessão); template facial cifrado agora guarda o **modelo** (`{"m": "sface", "v": [...]}`; lista antiga = `facenet`).
- `app/deps.py` — `usuario_atual` confere: token do mesmo aparelho do header `X-Dispositivo-Id`, sessão ativa, aparelho não bloqueado. `conta_atual` marca `ultimo_acesso_em` do vínculo (no máx. a cada 10 min).
- `app/services/senha_policy.py` — NIST 800-63B: mín. `SENHA_MIN`=10, lista de senhas comuns BR, sem CPF/e-mail/nome, sem sequência.

### Biometria (sem TensorFlow)
- `app/core/modelos.py` — registro de modelos com **SHA-256 fixado** + download conferido; `python -m app.core.modelos baixar` (para o Dockerfile).
  - YuNet `8f2383e4…`, SFace `0ba9fbfa…`, MiniFASNetV2 anti-spoof `af2381b8…` (suriAI, Apache-2.0, `models/best/98.20/best_model.onnx`), face_landmarker `64184e22…`.
- `app/services/face_engine.py` — `MotorOpenCV` (YuNet + SFace + MiniFAS via `cv2.dnn`) e `MotorDeepFace` (legado). Instâncias por thread. Escolha: `BIOMETRIA_MOTOR=opencv|deepface`.
- `app/services/biometria_service.py` — reescrito: além da sequência (liveness_logic), **consistência de identidade** (início/meio/fim têm de ser a mesma pessoa — mata troca de rosto no meio), anti-spoof por quadro amostrado, `cadastrar()` devolve `{vetor, modelo}`, `verificar(template=...)` recusa template de modelo diferente (409 "refaça a biometria"). `template_de_documento()` para KYC.
- `app/services/landmarks_service.py` — usa `core/modelos`; landmarker por thread.
- `app/services/liveness_logic.py` — modos fixos: **cadastro** = piscar 3x + sorrir + virar esq. + virar dir.; **login** = piscar 3x. (já estava no commit 6d225cf)
- Testado de verdade (fora do pytest) numa foto real: YuNet 17 ms; SFace mesma pessoa 1.000 / espelhada 0.912; anti-spoof roda; MediaPipe 478 pontos + 52 blendshapes. Script: ver seção 6.

### KYC / KYB (documentos)
- `app/core/arquivos.py` — tipo por **magic bytes** (JPEG/PNG/WEBP/PDF), limite antes de decodificar, PDF com conteúdo ativo (`/JavaScript`, `/OpenAction`, `/Launch`, `/EmbeddedFile`…) ou criptografado é recusado.
- `app/services/ocr_service.py` — Tesseract (`por`) + pré-processamento OpenCV; extração pura e testável: `encontrar_cpfs` (com DV), `encontrar_datas`, `nome_confere` (tolerante a OCR), **`ler_mrz`** (TD1/TD3 com dígitos ICAO 7-3-1), `ler_qr`. Provedor: `DOCUMENTO_PROVEDOR=auto|tesseract|sem_ocr|stub` (`auto` = tesseract se existir, senão `sem_ocr` → análise humana).
- `app/services/documento_service.py` — `analisar_documento_pessoa` (CPF/nome/nascimento/validade/MRZ/QR + **rosto do documento × selfie**) → `aprovado | em_analise | reprovado` com motivos; nunca aprova às cegas. `analisar_documento_empresa` (pypdf/OCR, confere CNPJ no texto). Imagem **não é guardada** (só SHA-256 + campos mascarados).
- `POST /usuarios` agora aceita `data_nascimento`, `celular`, `documento {tipo, frente, verso}`; KYC reprovado = conta **não** criada (caso registrado). `KYC_DOCUMENTO_OBRIGATORIO` (padrão 1; proibido 0 em produção).
- `app/routers/identidade.py` — `GET /identidade/kyc`, `POST /identidade/documentos`.
- Admin: `GET /admin/kyc/casos`, `POST /admin/kyc/casos/{id}/decidir?aprovar=`.

### PJ por porte, equipe, folha
- `app/services/politica_pj.py` — **MEI**: só o titular é admin, convidados só operador (com alçada)/consulta, até titular + `MEI_MAX_FUNCIONARIOS`(1) + 1. **PME**: até 30, todos os papéis, dar poder exige o rosto de quem concede. **GRANDE**: até 500, operador sempre com alçada, **4 olhos na gestão de acesso** (se ≥2 admins), e **2 aprovações** acima de `LIMITE_DUAS_APROVACOES_REAIS` (250 mil).
- `app/services/equipe_service.py` — convite por **CPF** (nasce `pendente`; GRANDE sensível = `aguardando` + operação pendente tipo `acesso`), aceite **pela própria pessoa com o rosto** (KYC ok), alterar papel/alçada, suspender/reativar/revogar, nunca fica sem admin. CPF sempre mascarado na API.
- `app/services/folha_service.py` — funcionários (cadastro separado do acesso ao app) e **folha**: o pedido só tem `funcionario_id`; o destino é resolvido no servidor = conta PF do CPF do funcionário. Alçada sobre o total → pendente tipo `folha`.
- `app/services/pagamento_service.py` — `criar_pendente` calcula nº de aprovações pela política; `decidir_pendente` com **N aprovadores atômico** (`registrar_aprovacao` com `FOR UPDATE`), criador nunca aprova, mesma pessoa não aprova 2x, `acesso` só admin, executa `transferencia | pagamento_cobranca | folha | acesso`. `transferir(..., sem_bloqueio_cautelar)` só para folha.
- `app/services/contas_service.py` — reescrito (PF com KYC; PJ exige KYC do representante + documento societário; `enviar_documento_empresa`).
- Rotas novas em `app/routers/contas.py`: `GET /empresas/atual/politica`, `GET|POST /empresas/atual/documentos`, `GET|POST /empresas/atual/vinculos`, `PATCH /empresas/atual/vinculos/{id}`, `POST …/{id}/suspender`, `POST …/{id}/reativar`, `DELETE …/{id}` (revoga), `GET /convites`, `POST /convites/{id}/aceitar|recusar`, `GET|POST|DELETE /empresas/atual/funcionarios`, `POST /empresas/atual/folha/pagar`.
- `app/routers/seguranca.py`: `POST /seguranca/dispositivos/{id}/bloquear` (derruba sessões do aparelho — fluxo celular roubado), `/desbloquear` (exige rosto), `GET /seguranca/atividade`, `GET /empresas/atual/auditoria`.

### Banco (models) — `app/db/models.py`
- `Usuario`: `data_nascimento`, `celular`, `kyc_status`.
- `Empresa`: `representante_usuario_id`, `kyb_status`.
- `Vinculo`: `usuario_id` **nullable**, `cpf`, `nome`, `email`, `celular`, `cargo`, `status` (`StatusVinculo`), `criado_por_usuario_id`, `aceito_em`, `status_em`, `ultimo_acesso_em`; unique `(empresa_id, cpf)`. `ativo` espelha `status == ativo`. Relacionamentos com `foreign_keys` explícito.
- `OperacaoPendente`: `descricao`, `aprovacoes_necessarias`, `aprovacoes` (JSON).
- `Dispositivo`: `bloqueado`, `bloqueado_em`.
- `RefreshToken`: `sessao_id`, `dispositivo_id`, `ip`, `user_agent`.
- `LogAuditoria`: `usuario_id`, `empresa_id` (index), `criado_em` index.
- Novas tabelas: `kyc_casos`, `documentos_identidade`, `documentos_empresa`, `funcionarios`.
- Repositório: métodos novos em `app/repositories/extras.py` (mixin herdado por `Repositorio`).

### HTTP — `app/main.py`
- Cabeçalhos de segurança em toda resposta (nosniff, DENY, no-referrer, Permissions-Policy, COOP, CSP `default-src 'none'` + `no-store` fora de /docs, HSTS em produção), `X-Request-Id`, erros **RFC 9457 problem+json** (mantém `detail` — o app lê esse campo; validação nunca ecoa o valor enviado), 500 genérico com log, `/docs` desligado em produção (`DOCS_HABILITADOS`), `GET /saude`, CORS com PATCH.

### Config nova (`app/core/config.py`)
`JWT_ISSUER`, `JWT_AUDIENCE`, `MFA_TOKEN_EXP_MIN`, `BIOMETRIA_MOTOR`, `MODELOS_DIR`, `MODELOS_DOWNLOAD`, `FACE_LIMIAR_COSSENO` (0.42), `FACE_DOC_LIMIAR_COSSENO` (0.30), `ANTISPOOF_LIMIAR`, `DOCUMENTO_PROVEDOR`, `KYC_DOCUMENTO_OBRIGATORIO`, `DOCUMENTO_MAX_BYTES`, `EMPRESA_DOCUMENTO_MAX_BYTES`, `LIMITE_DUAS_APROVACOES_REAIS`, `MEI_MAX_FUNCIONARIOS`, `SENHA_MIN`, `DOCS_HABILITADOS`, `ADMIN_IPS_PERMITIDOS`. Produção recusa: documento stub, KYC desligado, motor desconhecido.

## 3. Contrato novo resumido (para o app)

```
POST /biometria/desafios {modo: "cadastro"|"login", login?} -> {desafio_id, modo, passos:[{id,instrucao}], ...}
POST /usuarios {nome,email,senha,cpf,data_nascimento,celular,biometria,documento:{tipo,frente,verso?}}
POST /auth/login -> {mfa_requerido, mfa_token, desafio}   (pessoa)
POST /auth/login/mfa {mfa_token, biometria} -> tokens       (sempre com X-Dispositivo-Id do MESMO aparelho)
POST /auth/refresh  (mesmo aparelho; header X-Dispositivo-Id obrigatório se a sessão tem aparelho)
Erros: application/problem+json {type,title,status,detail,request_id,(erros)}
```

## 4. Pesquisa já feita (fontes)
- OpenCV YuNet/SFace e limiares (cosseno 0.363 no LFW): https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html
- Anti-spoof ONNX (contrato: crop 1.5x, RGB, letterbox 128, /255, saída [real, spoof]): https://github.com/suriAI/face-antispoof-onnx
- Argon2id OWASP (m=19MiB,t=2,p=1): https://Www.wikipedia.org/wiki/Argon2
- JWT BCP RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- MEI 1 funcionário / PLP 186/2026 (2 funcionários, não confirmado): https://www.gov.br/memp/pt-br/teto-do-mei
- Container Apps + Key Vault references: https://learn.microsoft.com/sk-sk/azure/container-apps/manage-secrets
- Postgres Flexible + managed identity (sem senha): https://learn.microsoft.com/da-dk/azure/postgresql/security/security-connect-with-managed-identity
- GitHub Actions → Azure por OIDC: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure
- OCR documentos BR (pré-processamento): https://sol.sbc.org.br/index.php/semish/article/download/36801/36587
- MRZ: https://updates.didit.me/blog/mrz-machine-readable-zone-technical-guide/

## 5. Próximos passos (nesta ordem)

Feitos na 2ª sessão (09/10): ~~1. testes~~, ~~2. migração~~, e do item 3: login 2 etapas, cadastro com
KYC (nascimento, celular, foto do documento, documento da empresa), equipe por CPF, convites recebidos
(`/convites`) e aprovações com N aprovadores. Detalhes na seção 7.

1. **Frontend — o que falta do item 3** (`app/`):
   - `lib/api.ts`: funcionários/folha (`GET|POST|DELETE /empresas/atual/funcionarios`,
     `POST /empresas/atual/folha/pagar` — só `funcionario_id`, o servidor resolve o destino), sessões
     (`GET /auth/sessoes`, `DELETE /auth/sessoes/{sid}`, `POST /auth/sessoes/encerrar-outras`), aparelhos
     (`GET /seguranca/dispositivos`, `POST …/{id}/bloquear`, `POST …/{id}/desbloquear` com rosto),
     atividade (`GET /seguranca/atividade`), auditoria (`GET /empresas/atual/auditoria`), KYC
     (`GET /identidade/kyc`, `POST /identidade/documentos` — para quem ficou `pendente`/`em_analise`).
   - Telas novas: folha (PJ), segurança (aparelhos/sessões/atividade — fluxo "celular roubado"), auditoria
     (PJ), e no perfil o status do KYC com botão para reenviar documento.
   - Equipe: alterar papel/alçada de quem já está ativo (`PATCH /empresas/atual/vinculos/{id}`, com rosto
     quando dá mais poder). Hoje dá para suspender/reativar/encerrar, não editar.
   - Testar o login e o cadastro **num celular de verdade** (câmera traseira no documento, prova de vida).
2. **Infra/Azure**: Dockerfile endurecido (python:3.12-slim, usuário não-root, `tesseract-ocr tesseract-ocr-por libgl1`, `python -m app.core.modelos baixar` no build, `MODELOS_DOWNLOAD=0`, uvicorn `--proxy-headers --no-server-header`), `infra/azure/main.bicep` (Container Apps + ACR + Key Vault RBAC + identidade gerenciada + Postgres Flexible com Entra/private access + Log Analytics; SPA no Static Web Apps), workflow GitHub Actions com OIDC (`azure/login`, sem segredo), `AZURE.md`, `SECURITY.md` (controles × OWASP API Top 10 / ASVS, roteiro de pentest).
3. Docs: atualizar `.env.example` com as variáveis novas; `COMO-RODAR-REMOTO.md` (local, não versionado) com `opencv-contrib-python` + mediapipe.

## 6. Ambiente / como rodar

- Backend: `cd backend && py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt`.
  **Não** instalar `opencv-python` junto (o mediapipe traz o `opencv-contrib-python`; dois `cv2` brigam).
- Testes: `.venv/Scripts/python.exe -m pytest -q` (rodam com `BIOMETRIA_STUB=1`, sem modelos).
- Modelos: `.venv/Scripts/python.exe -m app.core.modelos baixar` (vão para `~/.cache/astro/modelos`).
- Biometria real local: `BIOMETRIA_STUB=0` (padrão do .env deve ser 0 fora dos testes).
- Tesseract no Windows: instalar o binário (UB-Mannheim) + idioma `por`, ou definir `TESSERACT_CMD`. Sem ele, `DOCUMENTO_PROVEDOR=auto` cai para `sem_ocr` (documento vai para análise humana).
- App: `cd app && npm run dev` (porta 8081). `VITE_API_URL=http://localhost:8000` para modo API.
- e2e do app contra o backend (2 cenários: cadastro PF+PJ; convite por CPF → aceite → pendente → aprovação):
  backend com `BIOMETRIA_STUB=1 CNPJ_PROVEDOR=stub KYC_DOCUMENTO_OBRIGATORIO=0 DOCUMENTO_PROVEDOR=stub DEPOSITO_DEMO=1`
  em `--port 8765` e `VITE_API_URL=http://localhost:8765 npx vitest run src/lib/api.e2e.test.ts`.
- **eslint no Windows**: com `core.autocrlf=true` o checkout vira CRLF e o prettier acusa `␍` em todo arquivo.
  Não é erro de código: rode `npx eslint . --rule 'prettier/prettier: off'` (0 erros hoje) e formate só o
  que mexer com `npx prettier --write --end-of-line lf <arquivos>`.

## 7. O que a 2ª sessão descobriu (09/10)

- **Bug no Postgres (v7)**: o Alembic guarda em `impl.memo["pg_enum"]`, durante TODO o `upgrade`, os ENUMs
  que já criou. Num banco vazio, a v6 cria `papel_usuario`/`tipo_pessoa`/`auth_metodo`, a v7 apaga e o
  `create_table` da v7 achava que eles ainda existiam. Corrigido na v7 (esquece os tipos apagados). Era o
  que aconteceria no primeiro deploy num Postgres novo (Render/Azure).
- **Bug no aceite de convite**: `aceitar_convite` fazia UPDATE em massa e relia o objeto antigo da sessão
  (`expire_on_commit=False`), devolvendo `status: pendente`. Corrigido com `populate_existing`.
- **Bug na conta GRANDE**: aprovar mudança de acesso dava `TypeError` (`_log(..., acao=...)` duplicado), então
  os 4 olhos nunca concluíam. Corrigido.
- **Bug no app**: o desafio de cadastro ia com o token de quem estava logado no navegador, e o `POST /usuarios`
  recusava. Cadastro agora vai sem credenciais (`postAnonimo`).
- **Relógio nos testes**: o JWT usa o relógio real (o PyJWT exige) e a validade da sessão no banco é conferida
  com `tempo.agora()` (simulado nos testes). Teste que pula muitos dias precisa de `refresh_token_exp_dias`
  maior (ver `test_pix_automatico`). Em produção os dois relógios são o mesmo.
- **Comportamentos novos que os testes antigos não previam** (corretos): token preso ao aparelho (header de
  outro aparelho = 401); o login com rosto já confia no aparelho, então o limite de "aparelho novo"
  (R$ 200/R$ 1.000) só vale para aparelho que perdeu a confiança; `confiar` em aparelho já confiável não
  confere o rosto (retorna direto).
- Postgres local sem admin/Docker: `pip install pgserver` no venv dá um Postgres 16 embutido (usado para
  testar as migrações; não está no `requirements.txt`).
