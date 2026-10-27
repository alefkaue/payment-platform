# Facial mais fácil e documento automático — 26/10/2026

Branch: `fix/facial-rg-automatico` (a partir da `main` em `2201ccb`). **Ainda não está no Azure.**

## O que foi arrumado

### Prova de vida (facial)
- Cadastro pede **2 ações** sorteadas (antes 4) e login pede **1** (antes 2). Piscar é sempre 2x.
- Cada passo só precisa **aparecer** na gravação: não exige mais a ordem e não reprova
  movimentos naturais (virar, sorrir ou piscar fora do passo).
- Limiares mais folgados (`liveness_logic.py`): sorriso 0.45 → 0.35, giro 0.22 → 0.15,
  frontal 0.08 → 0.12, 1 quadro virado basta (antes 2). O app (`liveness.tsx`,
  `captura-facial.ts`) acompanha.
- Luz ruim e óculos **não recusam mais**: o servidor só registra no log. O app só orienta
  distância/centro (bem folgados) e escuro extremo (`qualidade-rosto.ts`).
- Basta 1 quadro frontal (antes 2). Anti-spoof `ANTISPOOF_LIMIAR` 0.5 → 0.3.

### Documento
- Na coleta acadêmica (`DOCUMENTO_VERIFICAR_IDENTIDADE=0`, como está no Azure) só confere se
  a foto **parece um RG/documento de identidade** (`documento_forma.py`, pontuação 3 → 2 só com
  texto, 2 → 1 com a foto 3x4). Não precisa ser real e não compara com o rosto da facial.
- **Sem tempo de análise:** o documento sai `aprovado` na hora (`documento_service.py`), sem
  fila de análise humana.

### Infra
- `infra/azure/Construir-Imagens.ps1`: novo parâmetro `-Ramo` (constrói de outra branch) e
  acha o Python do Azure CLI instalado em zip (`~/.local/azure-cli/python.exe`).

### Testes
- Backend: `test_liveness.py` e `test_documento_coleta.py` atualizados para as regras novas.
  Nenhuma falha nova em relação à `main` (as que sobram são falta de `cv2`/OpenCV no PC do SENAI).
- Front: `qualidade-rosto.test.ts` atualizado; 291 passam. `liveness.test.tsx > aguarda a
  resposta assíncrona...` já falhava na `main` antes desta mudança.

## Estado do Azure (assinatura do Gustavo, `d84028eb-…`)
- Postgres `pg-astro-lpsmd35drh7ng`, `astro-api` e `astro-front` **ligados** (22:07).
- Site: https://astro-front.blackfield-6387536e.canadacentral.azurecontainerapps.io
- API: https://astro-api.blackfield-6387536e.canadacentral.azurecontainerapps.io (`/saude`, `/pronto`)
- Imagem no ar: `e17f5c7` (versão antiga, **sem** estas correções).

## O que falta fazer
1. **Construir as imagens.** `Construir-Imagens.ps1` falhou às 22:05 (os dois jobs). Os jobs
   `astro-build-api` e `astro-build-front` ficaram criados no grupo `rg-astro-academico`. Ver o
   motivo nos logs da execução (portal → job → Execuções → Logs) ou no Log Analytics. Os tokens
   `kaniko-*` do ACR já foram apagados.
   ```powershell
   $sha = git rev-parse origin/fix/facial-rg-automatico
   .\infra\azure\Construir-Imagens.ps1 -Alvo api   -Ramo fix/facial-rg-automatico -Sha $sha
   .\infra\azure\Construir-Imagens.ps1 -Alvo front -Ramo fix/facial-rg-automatico -Sha $sha
   ```
2. **Publicar** (não há migração nova de banco nesta mudança):
   ```powershell
   $acr = 'acrastrolpsmd35drh7ng.azurecr.io'
   az containerapp update -g rg-astro-academico -n astro-api   --image "$acr/astro-api:$sha"
   az containerapp update -g rg-astro-academico -n astro-front --image "$acr/astro-front:$sha"
   ```
   Depois conferir `/pronto` e testar cadastro (facial + RG) no navegador.
3. **Cuidado com a `main`:** o workflow `azure.yml` roda no push da `main` e publica na
   **outra** assinatura (`361ca85d-…`, `acrastroaiznuxvyssyui`), não na do Gustavo. Combinar com
   o grupo antes de fazer merge.
4. Contas que já estão `em_analise` no banco continuam assim. Aprovar pela área de admin
   (`/admin`, casos KYC) ou mandar o documento de novo depois do deploy.
5. Quando acabar a apresentação, desligar para poupar crédito:
   `az postgres flexible-server stop -g rg-astro-academico -n pg-astro-lpsmd35drh7ng`.
