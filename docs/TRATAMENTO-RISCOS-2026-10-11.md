# Tratamento de riscos — 11/10/2026

## Resultado

Cartão: reduzir riscos do aplicativo e banco, mantendo Pix/documentos como
simulações e sem implantação na Azure.

Status: parcial quanto à eliminação de todos os riscos; melhorias locais abaixo
implementadas e verificadas. Não existe garantia de ausência de vulnerabilidades.

Commits: nenhum nesta etapa; alterações locais sobre 6998cd3d8f8c1dab9051531522b86f3e3aded8c5.
Não houve push ou deploy.

### Mudanças e evidências

- Segredos de webhook cifrados com Fernet, contexto da empresa e chaves separadas;
  rotação e rejeição de conteúdo adulterado testadas. Migração ea27104b9910 amplia
  a coluna sem truncar dados; downgrade recusa valores incompatíveis.
- Limites de cadastro, renovação, recuperação, desafio facial e consulta de chave
  Pix reservados atomicamente no PostgreSQL. A regressão reproduziu 12 aceites
  com teto 3 antes; agora apenas 3 reservas concorrentes são aceitas.
- Validação e extração de PDF em subprocesso sem segredos no ambiente, timeout,
  limite de concorrência e quotas de CPU/memória no Linux. Não é uma sandbox
  completa de sistema operacional; OCR e biometria ainda exigem isolamento adicional.
- Auditoria mínima transacional em troca de senha, bloqueio/desbloqueio de
  dispositivo, decisão KYC, alteração de vínculo, confiança de dispositivo e
  limite financeiro. Falha nessa gravação impede confirmação da alteração.
  O registro mínimo usa ator sistema; a trilha complementar identifica o contexto.
- 22 rotas falsas retornam 404 neutro antes de ler corpo ou acessar aplicação/banco.
  Elas reduzem exposição e registram sondagens sem dados brutos; não impedem
  descoberta de rotas legítimas nem substituem autorização.
- Prontidão externa agora consome limite de requisições; somente probes locais
  compatíveis com as condições definidas mantêm a isenção.
- Benefícios bloqueados no boot em produção, inclusive na demonstração pública.
  A flag de demonstração não libera stub facial, dispensa DPoP ou remove TLS.
- API/interface declaram valores fictícios e ausência de autenticação documental.
- Auditoria semanal de dependências e SBOM frontend preparados no workflow.
- Template Azure preparado com origem privada e WAF gerenciado; não compilado,
  criado ou implantado. Front Door Premium exige custos e aprovação da conexão
  privada quando houver implantação autorizada.
- Backups e logs brutos antigos conhecidos cifrados fora do Git, com leitura
  verificada antes de retirar originais. Chaves e arquivos têm permissões restritas;
  comprometimento do mesmo usuário/host continua sendo um risco.

### Arquivos alterados

- `.env.example`
- `.github/workflows/backend.yml`
- `AZURE.md`
- `app/package-lock.json`
- `app/package.json`
- `app/src/routes/__root.tsx`
- `backend/app/core/arquivos.py`
- `backend/app/core/config.py`
- `backend/app/core/limites.py`
- `backend/app/core/perimetro.py`
- `backend/app/db/base.py`
- `backend/app/db/models.py`
- `backend/app/main.py`
- `backend/app/repositories/extras.py`
- `backend/app/repositories/repository.py`
- `backend/app/routers/biometria.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/documento_service.py`
- `backend/app/services/pix_service.py`
- `backend/tests/conftest.py`
- `backend/tests/test_config_producao.py`
- `backend/tests/test_perimetro.py`
- `docker-compose.yml`
- `docs/INVENTARIO-RISCOS-2026-10-10.md`
- `infra/azure/main.bicep`
- `app/src/components/payflow/AvisoSimulacao.test.tsx`
- `app/src/components/payflow/AvisoSimulacao.tsx`
- `backend/alembic/versions/ea27104b9910_segredo_webhook_cifrado.py`
- `backend/app/core/pdf_worker.py`
- `backend/app/core/segredos_webhook.py`
- `backend/scripts/cifrar_webhooks.py`
- `backend/tests/test_auditoria_atomica.py`
- `backend/tests/test_limites_atomicos.py`
- `backend/tests/test_pdf_worker.py`
- `backend/tests/test_segredos_webhook.py`
- `docs/TRATAMENTO-RISCOS-2026-10-11.md` (este relatório).

### Testes

- Backend SQLite: 616 passaram / 45 pulados.
- Backend PostgreSQL: 632 passaram / 29 pulados, em quatro bancos descartáveis;
  os 661 casos coletados concluíram sem falhas. Banco de clientes não usado como fixture.
- Privilégios/migrações: 28 passaram; upgrade/downgrade/upgrade e alembic check
  passaram em banco isolado. Downgrade com segredo cifrado recusou truncamento.
- App: 258 passaram / 2 pulados; TypeScript, lint dos arquivos alterados e build HTTPS passaram.
- npm audit: zero vulnerabilidades conhecidas reportadas; SBOM com 588 componentes.
- Auditoria de privilégios e conciliação do banco local passaram.
- Migração aplicada ao banco local; segredos HMAC mantidos após cifragem e
  conteúdo das demais tabelas preservado. Backup novo cifrado com leitura verificada.
- Sintaxe Compose validada sem resolução de ambiente; não houve execução via
  Compose. O arquivo `.env` privado ainda precisa ser preparado para esse uso.
- Busca dos segredos locais conhecidos no conjunto alterado sem achados;
  git diff --check passou antes deste relatório.
- API local respondeu com modo simulação; prontidão e site responderam HTTP 200.

As suítes se sobrepõem; os números não representam ataques distintos. Auditorias
são instantâneos e não detectam necessariamente vulnerabilidades desconhecidas.

### O que NÃO foi feito e por quê

Sem deploy Azure por instrução do usuário; CLI/Bicep não disponíveis para validar
compilação. Sem publicação Git nesta etapa. Sem fornecedores de Pix/autenticação
real porque o objetivo definido é simulação. Sem certificado de segurança,
reclassificação de usuários antigos, teste físico de biometria ou RLS improvisado.
O estado individual dos 18 riscos está no
[inventário atualizado](INVENTARIO-RISCOS-2026-10-10.md).

### Problemas que vi fora do escopo

Dados cadastrais ainda consultáveis no banco; papel da API compartilhado;
contadores de falhas de login/rosto ainda não totalmente atômicos; outras ações
com auditoria posterior; processamento nativo parcialmente no processo principal.
Retenção, restauração definitiva, isolamento operacional, dispositivos reais e
limites distribuídos precisam de trabalho e evidência próprios.

### Como testar na mão

1. Abrir http://127.0.0.1:8081/ e conferir o aviso de simulação.
2. Consultar http://127.0.0.1:8765/ e `/pronto`; acessar `/api/debug/config`
   e confirmar resposta 404 neutra.
3. Executar os testes test_limites_atomicos, test_segredos_webhook,
   test_auditoria_atomica, test_pdf_worker e test_perimetro usando somente banco
   descartável. Fixtures recriam tabelas: nunca indicar o banco dos clientes.
4. Para outra instalação, fornecer WEBHOOK_KEYS persistente e separado das
   chaves JWT/embeddings; aplicar Alembic e scripts/cifrar_webhooks.py usando
   DATABASE_MIGRATION_URL. Guardar chaves antigas durante rotação até migrar os
   registros; nunca enviar chaves ao Git, logs ou frontend.
5. Conferir scripts/auditar_runtime.py e scripts/verificar_banco.py com credencial
   restrita. Guardar chave de backup separadamente antes de qualquer restauração.

Referências: [Fernet e rotação](https://cryptography.io/en/latest/fernet/),
[locks transacionais PostgreSQL](https://www.postgresql.org/docs/16/explicit-locking.html),
[origem privada Container Apps/Front Door](https://learn.microsoft.com/en-us/azure/container-apps/front-door-custom-virtual-network-private-link).
