# Handoff: senha/TOTP pronto no código, falta subir no Azure (16/10/2026)

Resumo para continuar de outro PC. O frontend de senha/TOTP está **pronto e testado**. O deploy no Azure
parou numa **migração de banco** que precisa ser aplicada antes de trocar a API.

## 1. Onde está o código
- `main` = `6543789` (front senha/TOTP), mais o commit `fix(db)` deste handoff, se já estiver no GitHub.
- Branch `feat/frontend-senha-totp`: mesmo conteúdo.
- O que mudou no app: ver a seção "Status" de [HANDOFF-FRONTEND-SENHA-TOTP.md](HANDOFF-FRONTEND-SENHA-TOTP.md).
  Resumo: pagamentos pedem **senha**; acima de **R$ 5.000**, também o **código TOTP**. O TOTP se ativa em
  **Segurança** (QR Code). O facial ficou só no login/cadastro.

## 2. Testes já feitos
- Front: `cd app && npm ci && npx vitest run` → **295 passando** (eram 282).
- Ponta a ponta contra backend local: 3/3 passando (cadastro, Pix, ativar TOTP, pagar R$ 5.000,01, replay recusado).
- Backend local (Python 3.12, `requirements-demo.txt`): só falham ~44 testes de documento/rosto, por
  falta do OpenCV (`cv2`). Nenhuma falha em pagamento/TOTP.

## 3. Por que o deploy parou
1. O workflow **"Azure Students - imagens de teste"** só autentica no Azure rodando na `main` (credencial
   federada `github-main` da identidade `id-astro-build`). As imagens do commit `6543789` **já estão no ACR**:
   - `acrastroaiznuxvyssyui.azurecr.io/astro-api:6543789ca509ce181ba21105656e82aa35afa693`
   - `acrastroaiznuxvyssyui.azurecr.io/astro-front:6543789ca509ce181ba21105656e82aa35afa693`
2. A API nova **não sobe**: `column usuarios.totp_segredo does not exist`. A migração Alembic
   `a7f0c2e14d55` (do backend do Matheus) não foi aplicada, porque no Azure a API roda com
   `RUN_MIGRATIONS=0` e o job de bootstrap/migração foi removido.
3. **Segundo problema:** no Postgres do Azure o usuário da API (`astro_app`) só pode dar UPDATE em colunas
   liberadas uma a uma (`backend/app/db/permissoes.py`, `COLUNAS_UPDATE`). As colunas do TOTP não estavam
   na lista, então ativar o TOTP daria "permissão negada". A correção no código acrescenta
   `totp_segredo` e `totp_passo_usado` a essa lista; o script abaixo aplica o mesmo GRANT no banco.
4. A API foi **revertida** para a imagem antiga (`7908dcb`), que está funcionando. O front do Azure não foi trocado.

## 4. Como terminar o deploy (≈10–15 min)
Precisa da conta Azure do Alef (`alef.nunes@portalsesisp.org.br`, assinatura Azure for Students) e do
Azure CLI.

```powershell
az login --use-device-code          # conta do Alef
git pull                             # na raiz do repo
powershell -ExecutionPolicy Bypass -File .\infra\azure\totp\subir-totp-azure.ps1
```

O script [`infra/azure/totp/subir-totp-azure.ps1`](../../infra/azure/totp/subir-totp-azure.ps1):
1. gera uma **nova senha para o admin do Postgres** (`astroadmin`) e mostra no final. **Passe para o Alef
   guardar**, porque a antiga dele deixa de valer;
2. cria um job temporário (`astro-migra-totp`) na rede privada, que roda
   [`migrar_totp.py`](../../infra/azure/totp/migrar_totp.py) como `astro_migrator`: adiciona as 2 colunas,
   libera o UPDATE delas para `astro_app` e marca o Alembic em `a7f0c2e14d55`;
3. apaga o job;
4. troca a imagem da API e espera `POST /auth/totp` responder **401** (rota nova no ar);
5. troca a imagem do front.

Se a migração falhar, o script para **antes** de trocar a API, e o site continua na versão antiga.

**Alternativa sem trocar a senha do admin:** o Alef roda no PC dele (onde estão as senhas):
`.\infra\azure\Preparar-Students.ps1 -Operacao create -Imagem <astro-api acima> -ImagemFront <astro-front acima> -Bootstrap -SomenteBootstrap`,
depois `az containerapp job start -n astro-bootstrap -g rg-astro-academico`. Esse job roda
`alembic upgrade head` + `restringir_runtime.py`, que já inclui o GRANT novo, desde que a imagem tenha o
commit `fix(db)`. Com a imagem `6543789`, aplicar o GRANT à mão:
`GRANT UPDATE (totp_segredo, totp_passo_usado) ON usuarios TO astro_app;`. Depois, trocar as imagens:
`az containerapp update -g rg-astro-academico -n astro-api --image <astro-api>` (e o mesmo para `astro-front`).

## 5. Depois de subir: roteiro de teste
Front: https://astro-front.blackwater-4ade2c64.canadacentral.azurecontainerapps.io
1. Entrar (ou criar conta **PJ**: o limite PF é R$ 5.000 por Pix, então o TOTP só aparece em PJ).
2. Depositar até R$ 10.000 (dinheiro de teste).
3. Pix ≤ R$ 5.000 → pede só a senha.
4. Pix > R$ 5.000 sem TOTP → aviso "Ativar agora".
5. Segurança → ler o QR no Google/Microsoft Authenticator → ativar.
6. Pix > R$ 5.000 com senha + código → passa; o mesmo código de novo é recusado.

Contas antigas continuam entrando normalmente: as colunas novas aceitam vazio (TOTP desativado).

## 6. Rodar localmente (sem Azure)
- API: venv Python 3.12 com `backend/requirements-demo.txt`; variáveis de `backend/tests/conftest.py`
  (`PII_KEYS`, `PII_INDEX_KEY`, ...) + `DEPOSITO_DEMO=1`,
  `CORS_ORIGINS=http://localhost:8081`; `uvicorn app.main:app --port 8765`.
- App: `cd app && VITE_DOC_OPCIONAL=1 VITE_API_URL=http://localhost:8765 npx vite dev` → http://localhost:8081.
- E2E: `VITE_API_URL=http://localhost:8765 npx vitest run src/lib/api.e2e.test.ts`.

## 7. Melhorias sugeridas (não aplicadas)
1. **TOTP pode ser trocado só com a sessão:** `POST /auth/totp` reinicia o 2º fator sem pedir senha nem o
   código atual. Quem roubar a sessão + senha cadastra o próprio autenticador. Exigir senha (e o código
   atual, se houver) para trocar.
2. **Limite PF = R$ 5.000/transação:** na prática, PF nunca usa o TOTP. Decidir se é intencional.
3. **Pendência PJ criada sem senha:** um operador cria pagamento pendente (acima da alçada) só com a sessão.
4. **Facial ainda em convites/acesso/desbloqueio/troca de senha:** avaliar trocar por senha/TOTP.
5. **Deploy:** recriar um job de migração permanente no `students.bicep`, para que migrações novas não
   derrubem a API de novo.
