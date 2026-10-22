# Banco ASTRO em MySQL 8 — progresso (pausado em 22/10/2026)

Versão MySQL 8 do banco PostgreSQL 16 do Astro, mais segura que o original.
Trabalho **separado**: branch `feat/banco-mysql`, pasta `db-mysql/`. Nada do
banco PostgreSQL, da aplicação ou da `main` foi alterado.

## Pronto e testado (servidor MySQL 8.0.46 local, porta 3307)

| Arquivo | Quem roda | O que faz | Status |
|---|---|---|---|
| `00_bootstrap_admin.sql` | admin | endurece o servidor, cria 5 bancos, 4 papéis e as contas (senha sorteada, TLS, bloqueio por erro) | ✅ |
| `01_ddl_tabelas.sql` | migrador | 32 tabelas InnoDB/utf8mb4, ~150 CHECK/UNIQUE/FK (originais + novas) | ✅ |
| `02_contexto_rls.sql` | migrador | substituto do RLS: contexto assinado por HMAC + funções de política | ✅ |
| `03_views_procedures.sql` | migrador | 32 views com o nome das tabelas, `transferir`, `astro_destinatario`, `astro_documento_usado`, relatórios, `verificar_banco` | ✅ |
| `04_triggers_auditoria.sql` | migrador | trilha com corrente de hash, tabelas append-only, regras de escrita (90 triggers) | ✅ |
| `05_dados_teste.sql` | migrador | **só laboratório**: dados fictícios + `lab_entrar_como` | ✅ |
| `06_privilegios.sql` | admin | GRANTs mínimos nas views (app, auditor, somente leitura) | ✅ |
| `07_testes_seguranca.sql` | conta da API | 22 testes negativos e positivos | ✅ todos com o resultado esperado |
| `99_fechar_janela_migracao.sql` | admin | tranca o migrador e apaga as rotinas de laboratório | ✅ |
| `testes/rodar_testes_lab.sh` | — | bateria completa (sem TLS, TLS 1.1, bloqueio por senha, replay, auditor, adulteração da trilha) | ✅ evidência em `testes/evidencias/resultado-lab.txt` |
| `ferramentas/gerar_auditoria.py` | — | gera os triggers de auditoria do 04 | ✅ |
| `integracao-app/contexto_mysql.py` | — | como a API assinaria o contexto no MySQL (exemplo, não ligado na app) | ✅ escrito |
| `integracao-app/teste_orm_lab.py` | — | prova de que os modelos SQLAlchemy da app funcionam nas views | ⏳ escrito, **ainda não rodou até o fim** |

## Onde parei / próximos passos

1. **Rodar `integracao-app/teste_orm_lab.py`** (a linha 50 acabou de ser corrigida). Passos:
   - recriar o laboratório (00 → 06);
   - como migrador, trocar a chave de contexto pela de teste do `conftest.py`:
     `UPDATE astro_privado.contexto_chave SET chave = FROM_BASE64('ISEhISEhISEhISEhISEhISEhISEhISEhISEhISEhISE=') WHERE id = 1;`
   - `LAB=<pasta dos .cnf> PYLIBS=<pasta com pymysql> python db-mysql/integracao-app/teste_orm_lab.py`
2. Rodar de novo `testes/rodar_testes_lab.sh` (já com os ajustes do C01/C07/C08) e atualizar a evidência.
3. **Fase 2 — Azure** (só código, sem executar): `infra/main.bicep` com Flexible Server B1ms, VNet sem IP público,
   `require_secure_transport`, TLS 1.2/1.3, `audit_log_enabled` (CONNECTION, DDL, DCL) → Log Analytics, Key Vault,
   backup/PITR, resource lock, alertas no Activity Log, Entra ID (`CREATE AADUSER`), passo a passo do Workbench
   (SSL "Require and Verify CA").
4. **Fase 4 — documentação**: `SEGURANCA-BANCO-MYSQL.md` (controle → ameaça → configuração → como verificar → evidência,
   diagrama Mermaid, matriz papéis × privilégios, PG × MySQL, CIS/ASB, LGPD, riscos residuais) e `README.md`
   com a ordem dos scripts no Workbench.
5. Diagrama ER: Workbench → Database → Reverse Engineer → schema `astro_dados`.

## Pontos já decididos (para a documentação)

- A API só enxerga views em `astro`. Sem o contexto assinado, a senha do banco sozinha não lê **nada**.
  No PG, `usuarios` e `vinculos` tinham leitura aberta: aqui ficou **mais seguro**.
- RLS novo em `contestacoes`, `operacoes_pendentes`, `pontos_movimentos`, `rendimentos`, `creditos_tributarios`
  e `logs_auditoria` (o original não filtrava essas tabelas).
- `totp_segredo` passa a exigir envelope cifrado (no PG estava em claro): **a app precisa incluir o campo em `CAMPOS`**.
- O segredo de webhook precisa estar cifrado (`enc:v1:`), o cartão só aceita a máscara e há CHECK nos formatos
  de hash, txid, NF-e e número de conta.
- Isolamento: `transferir` usa READ COMMITTED + `FOR UPDATE` em ordem de id. A conciliação usa REPEATABLE READ
  com snapshot consistente.
- **Riscos residuais:**
  - O contexto fica preso à conexão + `tx` + 35 s, mas não ao id interno da transação, como era no PG.
  - O escopo assinado libera ler a carteira de destino (igual ao original).
  - A trilha de auditoria serializa as escritas auditadas.
  - Para rotacionar chaves PII nas tabelas append-only, é preciso remover e recriar o trigger numa janela de manutenção.
- Na Azure: validate_password via `CALL mysql.az_install_validate_password_plugin();`; o restante dos
  parâmetros do 00 (Parte A) entra pelo Bicep.

## Laboratório local (fora do repositório)

Servidor de teste: `mysql-8.0.46-winx64` (zip em Downloads), `--defaults-file` com `port=3307`, dados no
scratchpad da sessão. As senhas sorteadas ficam em arquivos `.cnf` **fora do Git**.
