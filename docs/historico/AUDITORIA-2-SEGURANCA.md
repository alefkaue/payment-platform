# Astro — Auditoria 2: segurança, sessões e integridade financeira (10/10/2026)

Feita em equipe por **Claude Code** (backend e segurança financeira) e **OpenAI Codex**
(frontend, ataques à API e revisão independente do Claude), em ciclos: diagnóstico →
correção → revisão cruzada → ataque às correções → integração → este relatório.
Complementa o `SECURITY_AUDIT.md` (auditoria 1). Relatórios de cada ciclo:
`relatorios/C1-frontend-adversarial.md`, `C2-revisao-cruzada.md`, `C3-ataque-as-correcoes.md`
(Codex) e `R1-logica-bancaria.md` (lógica bancária × BCB). O ciclo C3 não tem relatório próprio: a
Codex foi interrompida pelo filtro de cibersegurança da OpenAI depois de escrever os testes
(`test_adv_c3_financeiro.py`, 38 casos); o resultado está na seção 1 e no commit `1d32f71`.

**Como foi coordenado.** Cada agente em uma cópia (git worktree) e branch próprios; a Codex
não altera `backend/app` — prova achados do backend com testes `xfail(strict=True)` e o
Claude corrige; o Claude revisa cada diff da Codex antes do merge. Nada é dado como
corrigido sem um teste que falha sem a correção e passa com ela.

**Classificação.** Confirmado = reproduzido por teste automatizado. Hipótese = não
reproduzido. Gravidade pelo risco real neste sistema, não pelo tipo genérico do problema.

## 1. Achados e correções

| ID | Gravidade | Componente | Problema (evidência) | Correção | Achou / corrigiu / revisou |
|---|---|---|---|---|---|
| R1-30 | **Alta** | Folha (`folha_service.py`) | Folha executada na hora não tinha idempotência: reenvio pagava todos de novo (`test_folha_idempotencia.py`, falha sem a correção) | Chave do app ou derivada de empresa+competência+funcionário+valor | Codex / Claude / Codex (C2) |
| C2-01 | **Alta** | Folha | A chave derivada usava o texto do valor: `300`, `3e2`, `300.0` pagavam de novo (`test_adv_c2_financeiro.py`) | Valor em forma canônica (2 casas) | Codex / Claude / Codex (C3) |
| C2-02 | **Alta** | Conciliação de pendências | Pix do próprio usuário com chave `pendente-{id}` fazia pendência de R$ 3.000 **não executada** virar "aprovada" (`test_conciliar_chave_publica_nao_prova_execucao`) | Chaves do cliente ganham prefixo `u:` (espaço de nomes separado das internas) + conciliação confere valor e destino | Codex / Claude / Codex (C3) |
| R1-07 | **Alta** | Limite de aparelho novo | Teto de R$ 1.000/dia era por aparelho: trocar de aparelho não confirmado abria outro teto (`test_teto_de_aparelho_novo_soma_todos_os_aparelhos`) | Soma entre todos os aparelhos não confirmados (IN BCB 491/2024, art. 9) | Codex / Claude / Codex (C2) |
| C1-03 | Média | Rotas de dinheiro | Header `Idempotency-Key` (anunciado em docs/CORS) era ignorado: reenvio debitava de novo (`test_adv_idempotency_header.py`) | Header ou corpo; diferentes = 400 | Codex / Claude / Codex (C2) |
| — | Média | Lote | Lote sem chave por item reenviado pagava tudo de novo (`test_lote_reenviado_no_mesmo_dia_nao_paga_de_novo`) | Proteção de remessa duplicada (conta+dia+itens) | Claude / Claude / Codex (C3) |
| R1-16 | Média | Pix Automático | Débito automático pulava os limites de valor do pagador (`test_debito_automatico_respeita_o_limite_do_pagador`) | Limites por transação e diurno/noturno aplicados | Codex / Claude / Codex (C2) |
| R1-39 | Média | Cobrança | A mesma NF-e em várias cobranças retinha o imposto de novo (`test_mesma_nota_nao_vira_duas_cobrancas`, concorrente em Postgres) | Nota já vinculada = 409, com a carteira travada | Codex / Claude / Codex (C2) |
| C2-05 | Média | Pendências | Reenvio com a mesma chave criava pendências duplicadas (Pix, folha, cobrança) | Pendência guarda a chave (índice único por empresa, migração `b9e1c2d3f4a5`) | Codex / Claude / Codex (C3) |
| R1-20 | Média | Rendimento | Job creditava qualquer data sobre o saldo atual (juros sobre saldo que não existia) | Só o próprio dia | Codex / Claude / Codex (C3) |
| C1-02 | Média | Front (sessão) | Tokens sobreviviam durante o logout; refresh atrasado podia restaurá-los | Limpeza imediata e versão de sessão | Codex / Codex / Claude |
| Rev. C1-02 | **Alta** | Front (sessão) | A correção acima descartava respostas também na rotação do refresh: um Pix já executado virava erro e a pessoa repetiria o pagamento (`sessao.test.ts`, falhava) | Só login/logout/queda mudam a versão | Claude (revisão) / Claude / Codex (C2) |
| C2-06 | **Alta** | Front (pagamento) | A chave de idempotência mudava a cada tentativa: falha de rede + novo toque = pagamento duplicado | Chave por intenção de pagamento (destino+valor), reaproveitada nas tentativas | Claude / Codex / Claude |
| C3-01 | Média | Pendências | Mesma chave com outro destino devolvia a pendência antiga (`test_pendente_mesma_chave_outro_pedido_conflita`) | Compara o pedido inteiro; diferente = 409 | Codex / Claude / — |
| C3-02 | Baixa | Idempotência (transição) | Pix gravado antes do prefixo `u:` era debitado de novo num reenvio depois da atualização | Busca também a forma antiga da chave do cliente | Codex / Claude / — |
| C3-03 | Baixa | Conciliação (transição) | Movimento antigo, de mesmo valor e destino, ainda contava como execução de pendência | Só aceita transação gravada como `APROVACAO` | Codex / Claude / — |
| — | Média | Banco (Postgres) | Chave de cliente de 80 caracteres + prefixo passava da coluna: erro 500 (só aparece no Postgres) | `transacoes.idempotency_key` 200 (migração `c4d5e6f7a8b9`) | Claude (rodando os testes da Codex no Postgres) / Claude / — |
| C2-04 | Baixa | Cobrança | Reenvio após resposta perdida dava 409 em vez do comprovante | Mesma chave, mesma conta, mesma transação = devolve o original | Codex / Claude / Codex (C3) |
| C2-03 | Baixa | Idempotência | Header em branco virava "sem chave" | 400 | Codex / Claude / Codex (C3) |
| C1-01 | Baixa | Front (cache) | Cache privado sobrevivia ao logout | Limpo em login/logout/troca/queda | Codex / Codex / Claude |
| A-16 | Média | Autenticação | Não havia troca/recuperação de senha | Troca com senha atual + rosto; recuperação neutra com prova de vida completa | Claude / Claude / Codex (C2) |
| A-15 | Média | Admin | Admin entrava só com senha | TOTP de uso único; produção não sobe sem segredo | Claude / Claude / Codex (C2) |
| — | Baixa | Política de senha | `123456789012` era aceita (sequência com volta) | Sequência com volta e invertida | Claude / Claude / — |
| — | Baixa | Auditoria | Cobranças, Pix Automático, limites e créditos não apareciam na trilha da empresa | `usuario_id`/`empresa_id` gravados | Codex / Claude / — |
| — | Média | Webhooks | Aviso gravado depois do commit: queda perdia o evento; reenvio duplicava | Outbox na mesma transação do dinheiro | Claude / Claude / Codex (C2) |
| — | Média | Pendências | Queda entre aprovação e resultado deixava a operação "executando" para sempre | Job de conciliação (nunca reexecuta) | Claude / Claude / Codex (C2, C3) |

## 2. O que foi atacado e resistiu (evidência)

Sessão e tokens: JWT `alg none`/HS512/RS256, assinatura trocada, claims (`sub`, papel, `exp`,
`nbf`, `iat`, `aud`, `iss`) adulteradas; refresh/MFA/recuperação usados como access; access
e refresh depois de logout, encerramento, bloqueio de aparelho, troca e recuperação de
senha; `X-Dispositivo-Id` trocado; prova DPoP reenviada, de outro método/endereço/horário/chave
— todos 401 (`test_adv_c1.py`, `test_adv_c2_auth.py`, `test_dpop.py`, `test_sessao.py`).
Autorização: IDOR em todas as rotas com id, `X-Conta` com vínculo suspenso/revogado,
escalada de papel, troca de método HTTP, mass assignment em cadastro, empresa, convite,
Pix, cobrança, recorrência, folha e webhook — recusados (`test_autorizacao_objetos.py`,
`test_adv_c1.py`). Força bruta e enumeração: aliases de login (CPF pontuado, e-mail com
maiúsculas/espaços) e `X-Forwarded-For`/`X-Azure-ClientIP` forjados não driblam limites;
login, recuperação e convite não revelam conta. XSS: payloads em descrição, motivo e erro
renderizados como texto; CSP sem `unsafe-inline` em script. CSRF: não se aplica (Bearer +
DPoP, sem cookie de sessão; CORS sem credenciais).

Dinheiro: valores 0, negativos, 3 casas, `NaN`, `Infinity`, enormes, texto, booleano —
recusados sem mover saldo. **Fuzz de invariantes** (`test_invariantes_financeiras.py`): 3
sementes × 120 operações aleatórias (Pix válidos/inválidos, chave repetida, cobrança com
NF-e, pagamento, estorno, MED, liberação de bloqueio, repasse, rendimento); depois de cada
passo a conciliação de `scripts/verificar_banco.py` confere soma total zero, nenhuma carteira
de cliente negativa, toda transação fechando em zero e saldo = último histórico. Passa em
SQLite e Postgres. **Concorrência real no Postgres** (`test_concorrencia_postgres.py`,
`test_concorrencia_extra_postgres.py`): saques simultâneos, mesma chave em paralelo, alçada
diária, estorno, decisão de MED, folha reenviada, mesma NF-e e liberação de bloqueio — cada
um acontece uma vez só com 12–20 chamadas ao mesmo tempo.

**Invariantes e exceções documentadas.** O total de todas as carteiras é sempre zero.
Dinheiro só nasce na CAIXA (depósito de demonstração, desligado em produção; rendimento),
que fica negativa nesse valor; repasse de tributo move de TRIBUTOS para FISCO. Nenhuma outra
operação muda o total.

## 3. Testes executados (resultado real, 10/10/2026)

| Suíte | Resultado |
|---|---|
| Backend SQLite | 444 passaram, 15 pulados (os de Postgres e a credencial restrita) |
| Backend Postgres 16 (pgserver local) | 457 passaram, 2 pulados (credencial restrita do CI) |
| Migrações Postgres vazio: upgrade → downgrade → upgrade → `alembic check` | OK, schema = modelos |
| App `vitest` / `tsc` | 117 passaram, 2 pulados / sem erros |

## 4. Riscos residuais (hipóteses e limites)

- **Recuperação de senha**: a etapa 2 recusa um pouco mais rápido quando ninguém confere
  (não roda o modelo de rosto); só aparece depois de uma prova de vida inteira, com limite.
- **Cadastro** distingue CPF/e-mail livre × já usado (201 × 409), com mensagem que não diz
  qual dado e limite por IP; consulta de chave Pix distingue existente × inexistente por
  finalidade (como o DICT), com limite e nome mascarado.
- **Pix sem chave de idempotência**: o app sempre manda (por intenção); um consumidor da API
  que não mande não tem proteção contra reenvio no Pix avulso (lote e folha têm proteção
  derivada).
- **XSS** continua sendo o caminho para usar a chave DPoP enquanto a página está aberta;
  a mitigação é a CSP (sem `unsafe-inline` em script) — no APK a CSP ainda não é aplicada.
- **Segredo TOTP único** para o admin de operação (admins múltiplos pedem cadastro por pessoa).
- **Concorrência** foi provada com Postgres local; a mesma suíte roda no CI a cada push.
- **Não testado**: biometria física (foto/vídeo/máscara/câmera virtual), atestação e pinning
  num celular real, infraestrutura publicada (WAF, TLS, headers do host).
- **Lógica bancária** (R1): comprovante sem E2E, QR decorativo, rendimento sem IR/IOF, split
  retido em 2026 (ano de teste, recolhimento dispensado) — são de produto/regulação, listados
  no `R1-logica-bancaria.md`, não falhas de segurança.

## 5. Depende de configuração manual (não feito por este trabalho)

Sem mudança na Azure/AWS. Para produção/pentest: segredos no Key Vault (incluindo
`ADMIN_TOTP_SEGREDO` se o admin for ligado), `AMBIENTE=producao`, CORS só com origens https
reais, `DOCS_HABILITADOS` vazio, TLS e HSTS na borda, Postgres sem acesso público e usuário
`astro_app` sem DDL, egress da API só para internet pública (fecha DNS rebinding de webhook),
WAF/rate limit na borda, logs para Log Analytics com alerta, backup testado. Lista completa:
`SECURITY_AUDIT.md` §6 e `AZURE.md`.

## 6. Recomendações para o pentest acadêmico

1. Atacar a **idempotência e a concorrência** com scripts (o app usa chave por intenção; a
   API aceita header ou corpo) — a conciliação `scripts/verificar_banco.py` dá a prova.
2. Atacar a **prova de vida** com foto, vídeo, tela, máscara e câmera virtual (é o controle
   menos testado automaticamente).
3. Tentar **burlar a atestação/pinning do APK** (Frida, APK reempacotado) e ver o que dá
   para fazer depois.
4. **Fluxos PJ**: alçada diária, assinatura conjunta na Grande, pendências fora de ordem.
5. Reportar pelo modelo do `PENTEST.md`; a equipe confere cada achado nos logs.
