# Astro — auditoria de segurança (10/10/2026)

Auditoria do repositório antes do pentest dos outros grupos. Tudo o que está como
**corrigido** tem teste automatizado citado e foi rodado; o que não pôde ser verificado
aqui está marcado como tal. Não há afirmação de que a aplicação é invulnerável.

Documentos relacionados: `THREAT_MODEL.md` (ameaças e riscos residuais), `ENDPOINTS.md`
(inventário gerado das rotas), `ACESSO_E_REGRAS_FINANCEIRAS.md` (regras), `SECURITY.md`
(como reportar e como testar), `PENTEST.md` (regras do teste), `SEGURANCA.md` (histórico
dos itens 1–10).

## 1. Método

1. Inventário das 101 rotas pelas dependências reais (`backend/scripts/inventario_endpoints.py`).
2. Linha de base: backend **203 testes ok**; app **19 ok / 2 pulados**; `tsc` com 1 erro
   (tipos de `scripts/pinos.mjs`, introduzido no item 10 — ver A-13).
3. Leitura dirigida por risco (autorização, dinheiro, autenticação, entrada externa) e
   **sondas**: testes descartáveis que tentam o ataque e imprimem o resultado, para só
   registrar achado com evidência.
4. Correção + teste de regressão para cada achado; suíte inteira de novo; revisão das
   próprias mudanças (duas falhas minhas achadas nessa revisão: A-13 e A-19).

## 2. Achados

| ID | Gravidade | Achado | Situação |
|---|---|---|---|
| A-01 | **Alta** | Empresa Grande: admin/aprovador sem alçada pagava **sozinho** acima do limite de assinatura conjunta | Corrigido |
| A-02 | **Alta** | Alçada só por operação: **fracionamento** (5 × R$ 900 numa alçada de R$ 1.000) e **lote** passavam sem aprovação | Corrigido |
| A-09 | **Alta** | Dependências com vulnerabilidades conhecidas: PyJWT 2.9.0 (21 avisos) e Starlette 0.38.6 (14 avisos) | Corrigido |
| A-04 | Média | **SSRF** nos webhooks: só se exigia `https://`; o servidor fazia POST para IP interno/metadados e o erro distinguia porta fechada de tempo esgotado | Corrigido |
| A-05 | Média | Operação pendente **não expirava**, era aprovável depois de o autor ser **suspenso**, e o autor **não conseguia cancelar** | Corrigido |
| A-06 | Média | **Bloqueio de conta por terceiro**: 10 senhas erradas de qualquer IP travavam a conta da vítima por 15 min | Corrigido |
| A-07 | Média | Teto de corpo (48 MB) só olhava `Content-Length`: requisição **chunked** passava por fora | Corrigido |
| A-15 | Média (residual) | Admin da plataforma entra **só com senha** (sem 2º fator) | Mitigado (lista de IPs obrigatória em produção); pendente |
| A-16 | Média (funcional) | **Não existia** troca nem recuperação de senha | Corrigido (backend e app) |
| A-08 | Baixa | `Idempotency-Key` repetida com **outro valor/destino** devolvia a transação antiga como se fosse a nova | Corrigido |
| A-10 | Baixa | `GET /cobrancas/{txid}` mostrava a qualquer logado o **CPF/CNPJ do pagador** e ids internos | Corrigido |
| A-11 | Baixa | `limite` sem teto em `/seguranca/atividade` e `/empresas/atual/auditoria` (consulta enorme) | Corrigido |
| A-03 | Baixa | Front mostrava "Pagar/Transferir" a quem é só **consulta** e exibia "Administrador" quando o papel não vinha | Corrigido (o servidor já recusava) |
| A-14 | Baixa | `docker-compose.yml` publicava a API em todas as interfaces (`8000:8000`) | Corrigido (`127.0.0.1:8000`) |
| A-17 | Baixa | Deploy antigo do Render derivava segredos do `DATABASE_URL` (corrigido no item 8) | **Rotacionar** os segredos daquele deploy |
| A-12 | Info | CORS com `allow_credentials=True` sem uso de cookie | Corrigido (`False`) |
| A-13 | Info | `tsc` quebrado por falta de tipos de `scripts/pinos.mjs` (regressão do item 10) | Corrigido |
| A-18 | Info | `backend/.venv` foi commitado em `96861fc` (ago/2026); não está mais versionado | Sem segredo encontrado; sem ação obrigatória |
| A-19 | Info | Após atualizar o FastAPI, o teste "nada abre sem login" passava **vazio** (2 rotas) | Corrigido (`app/core/rotas.py`) |
| A-20 | **Alta** | **Cadastro com documento quebrava no Postgres** (500): o hash "frente:verso" (129 caracteres) não cabia na coluna de 64. O SQLite dos testes não confere tamanho | Corrigido (migração `e5f6a7b8c9d0`, não destrutiva) |
| A-21 | Média | **Idempotência sob concorrência**: pedidos simultâneos com a mesma chave davam 500 em vez de devolver a transação (o dinheiro ficava certo) | Corrigido (chave conferida de novo depois do lock) |

### A-01 — Assinatura conjunta furada na Grande (Alta)
- **Evidência**: sonda — admin da Grande, `LIMITE_DUAS_APROVACOES_REAIS=5000`, Pix de R$ 6.000 → **200** (executado). A regra só disparava para quem tinha alçada.
- **Correção**: `pagamento_service.motivo_aprovacao` — acima do limite, qualquer pessoa gera pendência (`assinatura_conjunta`). Quem lança conta como uma das assinaturas **se** tem poder de aprovar aquele valor (admin/aprovador dentro da alçada) → falta 1; operador → faltam 2 (`criar_pendente`). Decisão documentada em `ACESSO_E_REGRAS_FINANCEIRAS.md`.
- **Testes**: `test_pj_regras_bancarias.py::test_admin_da_grande_nao_paga_sozinho_acima_do_limite`, `::test_pme_continua_com_admin_sem_limite`; os de 2 aprovações já existentes continuam passando.

### A-02 — Fracionamento e lote (Alta)
- **Evidência**: sondas — operador com alçada R$ 1.000: 5 × R$ 900 → `[200, 200, 200, 200, 200]`; lote 5 × R$ 900 → 5 × `concluida`.
- **Correção**: alçada **diária por pessoa** (`vinculos.alcada_diaria`, migração `d4e5f6a7b8c9`, não destrutiva; nula = igual à alçada). Soma do dia (BRT) do que a pessoa tirou da carteira, sem contar o executado por aprovação. Conferida antes (para responder rápido) **e de novo dentro do lock da carteira** (`_checar_alcada_diaria` → `AlcadaDiariaExcedida` → pendência), então requisições simultâneas não passam juntas. Vale para Pix, lote, folha e pagamento de cobrança. Aumentar a alçada diária é "dar poder" (rosto; quatro olhos na Grande).
- **Testes**: `test_fracionar_nao_dribla_a_alcada`, `test_lote_nao_dribla_a_alcada`, `test_alcada_diaria_conferida_dentro_do_lock`, `test_alcada_diaria_maior_permite_varias_no_dia`, `test_operacao_aprovada_nao_gasta_a_alcada_de_quem_aprova`, `test_alcada_diaria_validada_e_aumento_e_sensivel`; concorrência real em `test_concorrencia_postgres.py::test_alcada_diaria_nao_estoura_em_paralelo` (**só no CI**, ver §4).

### A-09 — Dependências vulneráveis (Alta)
- **Evidência**: `pip-audit -r requirements.txt` — PyJWT 2.9.0 (ex.: cabeçalho `crit` não validado, assinatura com caracteres fora do base64url) e Starlette 0.38.6 (ex.: `request.url` reconstruído sem validar Host/caminho — a prova DPoP usa `request.url.path`).
- **Correção**: `fastapi==0.143.0`, `starlette==1.7.0`, `PyJWT==2.15.1` (`requirements.txt` e `requirements-demo.txt`). `pip-audit` → *No known vulnerabilities found*. Suíte inteira passa.
- **JS**: `npm audit --omit=dev` → 0. Em dev, 3 moderadas em `uuid` via `@capacitor/cli` (ferramenta de build, não vai no app); a correção exige atualização com quebra da CLI — pendente.

### A-04 — SSRF em webhooks (Média)
- **Evidência**: `WebhookCreate` só tinha `pattern=r"^https://"`; `_enviar` guardava `erro: {exceção}`.
- **Correção** (`webhook_service`): só `https`, portas 443/8443, sem usuário/senha na URL, sem nomes internos (`localhost`, `.internal`, `.local`…) nem IP literal não público (inclui IPv4 mapeado em IPv6); na entrega, o nome é **resolvido e todos os endereços precisam ser públicos**; sem seguir redirecionamento; erro guardado genérico.
- **Testes**: `test_seguranca_api.py::test_webhook_recusa_destino_interno` (11 casos), `::test_nome_que_resolve_para_rede_interna_nao_recebe`, `::test_cadastro_de_webhook_interno_da_400`.
- **Residual**: *DNS rebinding* entre a conferência e a conexão (o httpx resolve de novo). Mitigar na infra: egress da API só para a internet pública (ver §6).

### A-05 — Ciclo de vida da pendência (Média)
- **Evidência**: sonda — operador suspenso → admin aprova a operação dele → **200 aprovada**; autor tenta cancelar → **403**.
- **Correção**: expira em `PENDENTE_VALIDADE_HORAS` (72); autor cancela (`aprovar=false` → `cancelada`); se o autor não tem mais vínculo ativo, a operação é **cancelada** em vez de executada. A conferência do autor fica **depois** da checagem de papel de quem decide (achado na revisão).
- **Testes**: `test_quem_lancou_pode_cancelar`, `test_pendencia_de_quem_foi_suspenso_nao_executa`, `test_pendencia_vence`.

### A-06 — Bloqueio de conta por terceiros (Média)
- **Correção**: 10 falhas por **conta + IP** travam só aquele IP; 50 por conta (todos os IPs) travam a conta (ataque distribuído). Mensagem igual para e-mail inexistente e senha errada (já existia).
- **Testes**: `test_forca_bruta.py::test_atacante_nao_trava_a_conta_da_vitima_de_outro_ip`, `::test_ataque_distribuido_trava_a_conta`, e os anteriores.
- **Residual**: botnet com > 50 IPs ainda trava a conta por 15 min (troca consciente: senão a senha fica aberta a força bruta distribuída).

### A-07 — Corpo chunked (Média)
- **Correção**: middleware ASGI `LimiteDeCorpo` (camada mais externa): sem `Content-Length`, lê até o teto e responde 413 sem ler o resto. Uma 1ª versão levantava exceção dentro do `receive` e o FastAPI a convertia em 400 — achado no teste e trocado.
- **Teste**: `test_corpo_grande_sem_content_length_e_recusado`.

### A-08, A-10, A-11, A-03, A-12, A-14
- A-08: `executar_movimento` compara origem/destino/valor da transação já gravada com a chave → `IdempotenciaConflitanteError` → **409**. Teste: `test_mesma_chave_repete_sem_duplicar_e_outra_operacao_da_409`.
- A-10: quem não é a empresa que cobra nem o pagador vê documento mascarado e sem ids internos. Teste: `test_quem_tem_o_txid_ve_a_cobranca_sem_dados_do_pagador`.
- A-11: `Query(ge=1, le=200)`. Teste: `test_listagem_tem_teto`.
- A-03: `nav.ts`, `_app.transferir.tsx`, `_app.inicio.tsx`. Sem teste de UI automatizado (o servidor é quem impõe; ver `test_papel_consulta_nao_movimenta`).
- A-12: `test_cors_nao_libera_origem_estranha_nem_credenciais`.
- A-14: `docker-compose.yml`.

### A-15 — Admin com fator único (Média, pendente)
Em produção o admin **não entra** sem `ADMIN_IPS_PERMITIDOS` (confere no login e em cada rota `/admin`). Falta um 2º fator (TOTP ou rosto). Recomendação: TOTP com segredo no Key Vault antes de expor o painel.

### A-16 — Troca e recuperação de senha (corrigido)
Era lacuna de produto: quem esquecia a senha não voltava. Sem link mágico por e-mail/SMS (seria a única prova):
- **Troca** (`POST /auth/senha`, logado): senha atual + rosto com prova de vida + política de senha; as outras sessões caem. Errar a senha atual conta no mesmo limite do login.
- **Recuperação** (`POST /auth/recuperacao` → `/auth/recuperacao/concluir`): e-mail/CPF + data de nascimento, depois **prova de vida completa** (as 4 ações do cadastro) no mesmo aparelho e chave DPoP. A etapa 1 responde igual exista a conta ou não (a pessoa vai cifrada no token); a etapa 2 recusa com a mesma mensagem. Token de uso único (10 min); senha nova derruba **todas** as sessões. Limite por IP (10/h) e por conta (5/h). Admin e conta sem data de nascimento não recuperam.
- Junto: a política de senha aceitava sequência longa (`123456789012`); agora confere a sequência com volta e invertida.
- **Testes**: `tests/test_senha.py` (11).
- **Residual**: a etapa 2 recusa mais rápido quando a etapa 1 não confirmou ninguém (não roda o modelo de rosto); a diferença só aparece depois de enviar uma prova de vida inteira, e há limite por IP/conta. O documento (KYC) não é pedido de novo: o rosto é conferido contra o template do cadastro, que já foi conferido contra o documento.

### A-20 e A-21 — achados pelo CI com Postgres (Alta / Média)
Os dois só aparecem no Postgres. Achados quando o CI `backend.yml` rodou pela 1ª vez e
reproduzidos localmente com um Postgres embutido (`pgserver`). A-20: `documentos_identidade.sha256`
passou a `VARCHAR(140)`. A-21: em `executar_movimento`, a chave é conferida de novo **com a
carteira travada** e o `IntegrityError` do `flush` também devolve a transação existente.
Testes: suíte inteira no Postgres (`test_kyc_*` e `test_mesma_chave_em_paralelo_gera_uma_transacao`).
O CI agora roda a **suíte inteira** no Postgres e `alembic check` (schema das migrações = modelos).

## 3. O que foi verificado e está correto (com evidência)

| Controle | Evidência |
|---|---|
| IDOR/BOLA: 19 rotas com id (transação, sessão, aparelho, chave Pix, vínculo, pendência, webhook, funcionário, cobrança, convite, admin) — atacante com conta e empresa próprias | `test_autorizacao_objetos.py::test_ninguem_usa_recurso_de_outro` (todas 403/404, vítima intacta) |
| Nenhuma das ~90 rotas protegidas responde sem login | `::test_sem_login_nada_protegido_responde` (percorre as rotas reais) |
| Mass assignment (`papel`, `saldo`, `status`, `liquido` no corpo) ignorado | sonda: cadastro → saldo 0, PF; Pix com campos extras → valores do servidor |
| Valores: negativo, zero, 3 casas, `NaN`, `Infinity`, > 12 dígitos, texto → 422 | sonda; `Dinheiro = Decimal(gt=0, max_digits=12, decimal_places=2)` |
| Movimento atômico: débito, crédito, histórico, split e cobrança na mesma transação; carteiras com `FOR UPDATE` em ordem fixa | `repository.executar_movimento`; concorrência real só no CI (§4) |
| Idempotência única no banco (`transacoes.idempotency_key UNIQUE`) com escopo por conta | testes existentes + A-08 |
| SQL injection: só ORM/parametrizado (nenhum SQL montado com texto do usuário) | leitura + `test_sql_injection_no_login_nao_entra` |
| XSS: React escapa; único `dangerouslySetInnerHTML` é CSS do shadcn sem dado do usuário; API responde JSON com CSP `default-src 'none'` e `nosniff` | `test_html_em_texto_livre_volta_como_texto_em_json` |
| Erros sem detalhe interno (problem+json com `request_id`); validação não ecoa o valor | `test_erro_interno_nao_vaza_detalhe`, `test_validacao_nao_ecoa_o_valor_enviado` |
| JWT: HS256 fixo, `iss`/`aud`/`exp`/`typ` exigidos, tipos de token separados; sessão com teto de 12 h e 30 min de inatividade; logout/encerrar sessão derruba na hora | `test_auth.py`, `test_sessao.py`, `test_dpop.py` |
| Tokens presos à chave do aparelho (DPoP); `jti` de uso único | `test_dpop.py` |
| Senha Argon2id (OWASP), política NIST (sem regra de composição), lista de comuns e dados pessoais | `senha_policy.py`, testes v9 |
| Uploads: tipo pelos bytes, teto antes de decodificar, PDF com JS/anexo recusado | `core/arquivos.py`, `test_documentos.py` |
| Segredos: nenhum segredo real no código nem no histórico (busca por chaves, tokens, URLs com senha); `.env` ignorado; produção não sobe sem segredos fortes | `git log -p` + `git grep`; `test_config_producao.py` |
| Front: sem source maps no build, só `VITE_API_URL`/`VITE_DEMO_SYNC_URL` públicos, build de produção recusa modo demonstração | `dist/client/assets`, `vite.config.ts` |
| Logs: JSON em produção com `request_id`; mensagem com quebra de linha não forja outra linha; falha da trilha não derruba Pix já feito | `test_log_json_tem_request_id_e_nao_deixa_forjar_linha`, `test_falha_na_trilha_nao_derruba_o_pix_ja_feito` |

## 4. Testes executados (resultado real)

| O quê | Resultado |
|---|---|
| Backend `pytest` | **250 passaram, 3 pulados** (antes: 203; inclui 3 da correção da facial) — os 3 pulados são os de Postgres |
| Suíte inteira no **Postgres 16** (Postgres embutido local) | **253 passaram** — inclui os 3 de concorrência; antes da correção A-20/A-21, 4 falhavam |
| Migrações no Postgres (sobe, desce, sobe) + `alembic check` | OK; schema igual aos modelos |
| App `vitest` | 19 passaram, 2 pulados |
| App `tsc --noEmit` | sem erros |
| App `eslint src scripts` | só `Delete ␍` (CRLF do checkout no Windows, arquivos não alterados) e 8 avisos antigos de fast-refresh |
| `pip-audit -r requirements.txt` | sem vulnerabilidades conhecidas |
| `npm audit --omit=dev` | 0 |

Rodar localmente: ver `SECURITY.md` §3.

## 5. Pendências e riscos residuais

1. **A-15** 2º fator do admin.
2. **Concorrência no Postgres** só provada quando o CI rodar (`backend.yml`).
3. **Usuário do banco**: o `DATABASE_URL` do Bicep usa o administrador do Postgres. O certo é um papel só com DML nas tabelas para a API e o dono do schema só para as migrações (ver §6).
4. DNS rebinding no webhook (A-04) — fechar com egress na infra.
5. `uuid` (dev) via `@capacitor/cli`.
6. Itens do `SEGURANCA.md` 10 ainda não testados num celular (Keystore, atestação, pinning).
7. O WAF Standard não tem regras gerenciadas e a origem do Container Apps é acessível sem WAF (já declarado no `PENTEST.md`).
8. Logs: o `LogAuditoria` fica na mesma base que a API escreve — um invasor com a credencial do banco poderia apagá-lo. Exportar para o Log Analytics (imutável para a API) cobre isso.

## 6. Ações manuais pendentes na Azure / AWS / VMs (não feitas por este trabalho)

- [ ] Gerar segredos novos (`AZURE.md` §2) e **rotacionar os do deploy antigo no Render** (A-17).
- [ ] `AMBIENTE=producao`, `CORS_ORIGINS` só com as origens https reais (+ `https://localhost` do APK), `DOCS_HABILITADOS` vazio.
- [ ] `ADMIN_IPS_PERMITIDOS` com o IP de quem administra (sem isso o admin fica desligado — é o esperado).
- [ ] IP real do cliente: Front Door → `FRONT_DOOR_ID`; VM com nginx → `PROXIES_CONFIAVEIS=127.0.0.1`.
- [ ] TLS em tudo (Front Door/Static Web Apps, ou certbot nas VMs); HSTS já sai da app.
- [ ] Postgres sem acesso público; criar `astro_app` (SELECT/INSERT/UPDATE/DELETE nas tabelas, sem DDL) para o `DATABASE_URL` da API e usar o dono só nas migrações.
- [ ] Egress da API: só internet pública (bloquear 10.0.0.0/8, 169.254.169.254 etc. no NSG/Security Group) — fecha o residual do A-04.
- [ ] WAF/rate limit na borda (Front Door ou Cloudflare); restringir a origem ao proxy quando o tier permitir.
- [ ] Segredos no Key Vault / Secrets Manager (o código já lê tudo de variável de ambiente).
- [ ] Logs da API para Log Analytics/CloudWatch com retenção; alerta em `login_bloqueado_tentativas`, 5xx e `operacao_cancelada`.
- [ ] Backup do Postgres e teste de restauração.
- [ ] GitHub: proteção do `main`, Dependabot e secret scanning ligados; variáveis do OIDC (`AZURE.md` §4).
- [ ] APK release: chave estável e `ATESTACAO_ASSINATURAS` (`AZURE.md`).

## 7. Ordem recomendada para as próximas correções

1. Rodar o CI `backend.yml` e conferir os 3 testes de Postgres e a migração.
2. Papel `astro_app` com menor privilégio + egress restrito (configuração, sem código).
3. 2º fator do admin (A-15).
4. ~~Troca e recuperação de senha com rosto (A-16)~~ (feito).
5. Testar no celular os itens do APK (Keystore, atestação, pinning, FLAG_SECURE).
6. Exportar a trilha de auditoria para fora do banco da API.
7. Atualizar `@capacitor/cli` quando houver versão sem o `uuid` vulnerável.
