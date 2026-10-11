# C1 — Frontend e testes adversariais da API

Data: 10/10/2026. Execução local no worktree `astro-gpt`, sem commit, sem alteração de `backend/app/` ou migrações. Foram lidos GPT.md, README.md, app/AGENTS.md, SECURITY_AUDIT.md, THREAT_MODEL.md, ACESSO_E_REGRAS_FINANCEIRAS.md, ENDPOINTS.md, PENTEST.md e docs/BANCO.md. A divisão com o Claude foi respeitada.

## Resultado e achados

Dois problemas de saída de sessão corrigidos no frontend; um problema de contrato de idempotência confirmado no backend, com duas provas xfail strict. Nenhuma tomada de conta, IDOR ou manipulação monetária adicional foi confirmada nos testes executados. Isso descreve a cobertura abaixo, sem garantia de ausência de outras falhas.

| ID | Gravidade real | Componente | Evidência (arquivo:linha ou teste) | Status |
|---|---|---|---|---|
| C1-01 | Baixa | Cache privado sobrevivia ao logout; limpeza na troca dependia do layout | `app/src/lib/auth.tsx:93`, `app/src/test/auth-adversarial.test.tsx` — quatro casos entrar/trocar/sair/expirar | Corrigido no front |
| C1-02 | Média | Tokens permaneciam durante logout em rede; refresh atrasado podia restaurá-los; logout atrasado podia apagar login novo | `app/src/lib/api.ts:555`, `app/src/lib/http.ts:144`, `app/src/lib/sessao.test.ts` — logout imediato, refresh atrasado, novo login e storage indisponível | Corrigido no front |
| C1-03 | Média | Header `Idempotency-Key` ignorado em transferência; reenvio debita novamente | `backend/tests/test_adv_idempotency_header.py::test_adv_header_idempotency_key_evitar_debito_repetido[10/20]`; `backend/app/routers/pagamentos.py:32` | Achado para o Claude (xfail) |
| C1-04 | Info | CPF/e-mail/chave Pix vão no caminho da requisição de consulta; possível retenção por logs de acesso | `app/src/lib/api.ts:734`, `GET /pix/consultar/{chave}` em ENDPOINTS.md | Já coberto |
| C1-05 | Info | Audit atual das dependências sem resultado: registry inacessível | `npm.cmd audit --omit=dev` retornou erro no endpoint de advisories | Não confirmado |
| C1-06 | Info | Proteção contra demo depende do nome do modo do build; publicação acidental de build customizado não demonstrada | `app/vite.config.ts:17`; build padrão recusado sem API; build development solicitado passou | Não confirmado |
| C1-07 | Info | XSS por descrições/erros; nenhum vetor explorável confirmado | `app/src/test/contestacao-estorno.test.tsx`, três payloads; `app/src/components/ui/chart.tsx:73` sem consumidor com entrada externa | Já coberto |
| C1-08 | Info | CSRF por cookie não autentica a API; CORS não permite credenciais | `backend/app/main.py:85`, `test_cors_nao_libera_origem_estranha_nem_credenciais`, `app/src/lib/http.ts:197` | Já coberto |

### C1-01 e C1-02 — correção e impacto

O provider agora limpa o QueryClient no login, logout e troca de conta, além da expiração já existente. Assim, qualquer consumidor de `trocarConta` recebe a limpeza; antes ela dependia do seletor do layout. A saída remove pessoa, contas e `payflow-session` sincronamente.

O logout captura o refresh da memória e inicia a revogação antes de apagar as credenciais locais. A limpeza ocorre antes de aguardar a resposta, inclusive sem sessionStorage. Não há limpeza tardia que apague credenciais de uma pessoa que entrou enquanto o logout estava pendente.

O cliente HTTP marca mudanças de tokens com uma versão. Respostas e renovações de uma sessão anterior não gravam tokens nem encerram um login posterior. A versão também é conferida depois de ler o corpo da resposta. A revogação remota continua sendo melhor esforço se a rede estiver indisponível; isso não mantém as credenciais locais.

### C1-03 — prova para o Claude

Pré-condições: pessoa autenticada em uma conta sintética com R$ 100; destinatário sintético com saldo zero. Dois POSTs em `/pagamentos/transferir`, cada um com `Idempotency-Key: c1-pagamento-unico`, JSON com destino e valor, sem o campo JSON `idempotency_key`.

- Mesmo valor R$ 10: esperado mesmo id e saldo R$ 90; obtido 200 duas vezes, ids 2 e 3, dois movimentos.
- Segundo valor R$ 20: esperado 409 e saldo R$ 90; obtido 200 e outro movimento.

Os dois testes foram executados inicialmente sem xfail e falharam nas assertivas de id/status. Depois receberam `@pytest.mark.xfail(strict=True, reason="ACHADO C1-03: ...")`. Não é corrupção da implementação de idempotência pelo JSON: esse caminho passa nos testes existentes. É divergência do contrato anunciado nos documentos e no CORS, com risco de débito duplicado para consumidores que usam o header. O frontend atual manda a chave no JSON (`api.ts`, transferência), portanto o achado não demonstra duplicação automática no fluxo normal do app.

Sugestão: adotar o header explicitamente nas rotas financeiras relevantes, definir precedência/conflito com o campo JSON e testar reenvio e mudança de operação. Quando corrigido, os xfails produzirão XPASS strict até o marcador ser removido. Não foi alterado o backend.

## Diagnóstico do frontend

| Dado | Armazenamento | Saída/expiração/troca |
|---|---|---|
| Access e refresh | Memória do módulo HTTP e sessionStorage `payflow-tokens` | Removidos imediatamente na saída/expiração; renovação antiga não os restaura |
| Conta selecionada | Memória HTTP e sessionStorage `payflow-conta-numero` | Removida na saída/expiração; substituída na troca |
| Nome/e-mail/CPF e contas | Estado do AuthProvider e sessionStorage `payflow-session` | Removidos na saída/expiração; pessoa permanece na troca PF/PJ da mesma identidade |
| Dados consultados | QueryClient em memória | Cache limpo em entrada/saída/expiração/troca |
| Id do aparelho | localStorage `payflow-dispositivo` | Permanece deliberadamente; identidade do aparelho, sem dados pessoais embutidos |
| Chave DPoP | IndexedDB `astro-chaves/chaves/dpop`, CryptoKey privada não exportável; memória; Android Keystore no APK | Permanece deliberadamente; chave do aparelho, não uma sessão. Logout invalida os tokens da família no servidor |
| Dados de demonstração | localStorage do banco mock, objetos em memória | Persistem por desenho da demonstração; não são credenciais da API. Não usar pessoas reais no demo |

A persistência da chave e do id não foi classificada como falha: apagá-los a cada logout transformaria cada login em aparelho novo. A suíte local não testa IndexedDB/Keystore em um aparelho físico; o caráter não exportável foi revisado no código `dpop.ts`, sem prova física do APK.

Busca em `app/src` por sessionStorage/localStorage/IndexedDB, console, HTML cru, href/src e VITE_*: tokens vão em header/corpo, sem token em navegação ou título. Títulos são estáticos. Não foi encontrado analytics transmitindo credenciais. Logs de erro genéricos existem no root/start/server; não foi demonstrado erro contendo CPF/token. C1-04 é caminho da API, não URL da tela: percent-encoding não torna CPF secreto. A retenção/redação dos logs do proxy não foi auditada neste ambiente.

Descrições, nomes, motivos, erros e copia-e-cola são texto React. As imagens ativas recebem câmera/documento local ou imagens fixas de boas-vindas. QR Pix é uma matriz SVG sintética; a seed não vira HTML ou URL. Clipboard recebe texto, sem executá-lo. O único `dangerouslySetInnerHTML` está no componente ChartStyle de CSS; não foi encontrado consumidor passando dados externos. `href` das notificações vem de mocks internos. Os testes de comprovante enviam `<img src=x onerror=alert(1)>`, `<script>alert(1)</script>` e `javascript:alert(1)` em descrição e erro e verificam ausência de elementos executáveis.

A API autentica com Bearer + DPoP e não lê cookie como identidade; não há credencial que um formulário de outro site faça o navegador anexar automaticamente. CSRF por autenticação ambiente não se aplica a esse contrato. CORS permite os métodos e headers usados pelo app, não habilita `allow_credentials`, e expõe `WWW-Authenticate`, necessário para distinguir 401 de sessão de 401 biométrico. XSS continua relevante: a chave não exportável pode assinar enquanto o código atacante roda na origem.

### Bundle, CSP, demonstração e autoridade

`npx.cmd vite build --mode development` passou, gerando dist/client e dist/server. A busca por JWT_SECRET, EMBEDDING_KEY, senhas de admin/teste, chave privada, client_secret, PostgreSQL com credencial e IP interno não encontrou segredo nos artefatos. O único match de `localhost:8000` foi um comentário de exemplo em dist/server/assets/api; não era URL efetiva nem segredo do cliente. Nomes e saldos de mocks são fictícios. Nenhum arquivo `.env` preenchido foi encontrado em app; há apenas `.env.example`.

Vite não habilita source maps explicitamente. VITE_API_URL e VITE_DEMO_SYNC_URL são configurações públicas. VITE_DOC_OPCIONAL está condicionado a `import.meta.env.DEV`, que é falso no build normal. Não foi encontrado overlay de debug próprio com credenciais.

`npx.cmd vite build` sem API/demo explícito falhou com a mensagem de proteção esperada. A guarda depende de `mode === production`; o build de development solicitado serve como demonstração e pode ser publicado se alguém o escolher. Não foi demonstrado que o pipeline de produção faça isso. `VITE_MODO_DEMO=1` é exceção deliberada. Não houve alteração de vite.config.ts.

`scripts/cabecalhos.mjs` usa hashes dos scripts inline, `object-src/base-uri/frame-ancestors 'none'`, `form-action 'self'`, `no-referrer`, e restringe conexão à API e dependências públicas usadas. Script não permite unsafe-inline. O comando direto `vite build --mode development` não roda o pós-build de cabeçalhos; o script `npm run build` roda. Foram revisados o gerador e seus testes existentes; não foi feita publicação para comprovar headers do host real.

Botões e biometria condicionais no cliente são UX. O servidor verificou papéis e recusou transferências/ações administrativas indevidas nos testes. `transferir` envia valor/destino e chave idempotente; folha envia funcionário/valor, sem confiar no destino injetado. Totais de faturas e estimativas de split calculados no cliente não autorizam pagamento; os valores efetivos são conferidos no servidor. A tela de depósito demo continua visível, mas a rota vem desligada por padrão e o backend de produção rejeita configuração demo. A visibilidade não demonstra crédito autorizado em produção.

## O que foi testado e passou

Os nomes sem outro prefixo nesta primeira tabela pertencem a `backend/tests/test_adv_c1.py`. Parametrizações fazem parte de cada ataque listado. Foram acrescentados 54 casos passando e dois xfails confirmados.

| Ataque tentado | Teste que passou / resultado |
|---|---|
| JWT alg none, HS512, RS256, assinatura trocada; sub/papel/exp/nbf/iat/aud/iss adulterados | `test_adv_jwt_manipulado_nao_autentica` — 401, sem acesso admin |
| exp/nbf/iat/aud/iss inválidos com assinatura válida de teste, isolando validação das claims | `test_adv_claims_invalidas_mesmo_com_assinatura_valida` — 401 |
| Refresh/MFA/recuperação como access; recuperação como MFA | `test_adv_tipos_de_token_nao_sao_intercambiaveis` — 401 |
| Access e refresh depois de logout, encerramento, bloqueio, reuso; X-Dispositivo-Id trocado | `test_adv_access_e_refresh_de_sessao_invalidada` — 401 |
| 0.001, -0, 10.005, enorme, texto, null, NaN, Infinity, booleano, objeto, lista | `test_adv_valores_invalidos_nao_movem_saldo` — 400/422, saldos intactos |
| Espaços, notação científica e decimal em string | `test_adv_decimal_equivalente_preserva_valor` — aceitos como números decimais equivalentes, valor exato; não são falhas |
| Saldo, origem, autor, papel, status, CBS/IBS/líquido injetados no Pix | `test_adv_mass_assignment_transferencia_e_conta` — origem autenticada e valores do servidor |
| X-Conta após suspensão/revogação | `test_adv_x_conta_de_vinculo_inativo` — 403/404 |
| Consulta/operador elevando papel, criando funcionário/webhook | `test_adv_papel_nao_admin_nao_gera_poder` — 403 |
| CPF pontuado, e-mail maiúsculo/com espaços, XFF/Azure ClientIP forjados | `test_adv_login_alias_e_headers_forjados_nao_driblam_limite` — mesmo limite, 429 |
| PUT/PATCH/DELETE para editar transação concluída | `test_adv_troca_metodo_nao_edita_transacao` — 405, saldo intacto |
| Recebedor abrindo MED da transação recebida | `test_adv_recebedor_nao_contesta_transacao` — recusado, saldo intacto |
| Folha com funcionário de outra empresa | `test_adv_folha_funcionario_de_outra_empresa` — não paga, saldos intactos |
| Pagar cancelada, pagar duas vezes, estornar duas vezes | `test_adv_cobranca_cancelada_paga_e_estorno_repetido` — recusado, saldo reconciliado |
| IDOR nas quatro ações de recorrência, reativação de vínculo, desbloqueio de aparelho, admin KYC/liberação/MED | `test_adv_idor_recorrencia_e_rotas_complementares` — 403/404 |
| Hash/template/token/segredo em respostas; headers de tecnologia/cookie | `test_adv_respostas_privadas_sem_segredos` — sem campos sensíveis pesquisados |
| Cadastro com saldo/papel/hash/tipo/id; empresa com representante/id/saldo; convite/PATCH com usuário/empresa/status | `test_adv_mass_assignment_cadastro_empresa_e_acesso` — autoridade preservada |
| Cobrança paga/split/transação injetados; recorrência ativa; funcionário inativo; destino alheio na folha; titular da chave Pix; segredo de webhook | `test_adv_mass_assignment_cobranca_recorrencia_folha_pix_e_webhook` — extras não mudam controle; segredo só na criação |
| Convite com CPF cadastrado vs. não cadastrado | `test_adv_convite_cpf_cadastrado_e_inexistente_mesmo_contrato` — 201, mesmo contrato, usuário não revelado |

Controles existentes também foram executados na suíte completa, complementando os ataques novos:

| Ataque tentado | Teste existente que passou |
|---|---|
| IDOR: transação, MED, sessão, apagar/bloquear aparelho, chave, X-Conta, alterar/suspender/revogar vínculo, pendente, webhook, funcionário, cancelar/estornar cobrança, aceitar/recusar convite, admin | `test_autorizacao_objetos.py::test_ninguem_usa_recurso_de_outro` |
| Percorrer todos os métodos das rotas protegidas sem login | `test_autorizacao_objetos.py::test_sem_login_nada_protegido_responde` — guarda contra inventário vazio |
| Cobrança consultável por txid sem revelar CPF/ids a terceiros | `test_autorizacao_objetos.py::test_quem_tem_o_txid_ve_a_cobranca_sem_dados_do_pagador` |
| Token/prova roubados, replay jti, método/endereço/horário/chave errados, DPoP alg none | `test_dpop.py::test_token_roubado_sem_a_chave_nao_serve`, `test_prova_capturada_nao_pode_ser_reenviada`, `test_prova_de_outro_endereco_metodo_ou_horario`, `test_prova_com_chave_privada_no_cabecalho_ou_alg_none`, `test_refresh_roubado_nao_renova_sem_a_chave` |
| MFA reutilizado, rosto/chave/aparelho alheios | `test_v9_seguranca.py::test_mfa_token_nao_e_reutilizavel`, `test_mfa_sem_rosto_ou_de_outro_aparelho_nao_entra`; `test_dpop.py::test_etapa_do_rosto_com_outra_chave_e_recusada` |
| Access após trocar senha/recuperar; recuperação fora do aparelho ou reutilizada | `test_senha.py::test_troca_exige_senha_atual_rosto_e_derruba_as_outras_sessoes`, `test_recuperacao_com_nascimento_e_rosto_troca_a_senha_e_derruba_tudo`, `test_recuperacao_e_de_uso_unico_e_presa_ao_aparelho` |
| Sessão estendida por refresh ou após inatividade | `test_sessao.py::test_inatividade_derruba_a_sessao`, `test_tempo_maximo_vale_mesmo_renovando_sempre` |
| Pagar cobrança com pagador diferente | `test_cobrancas.py::test_cobranca_para_pagador_especifico` |
| Transferir para si mesmo, Pix inexistente | `test_pix_chaves.py::test_chave_inexistente_e_pagar_a_si_mesmo` |
| Chave JSON repetida, outro valor/destino/conta | `test_seguranca_api.py::test_mesma_chave_repete_sem_duplicar_e_outra_operacao_da_409`; `test_transferencias.py::test_idempotencia_por_conta` |
| Aprovar a própria, aprovar novamente, acima da alçada; pular a quantidade de assinaturas | `test_pj.py::test_alcada_e_dupla_aprovacao`, `test_aprovador_nao_aprova_acima_da_propria_alcada`; `test_v9_seguranca.py::test_grande_duas_aprovacoes_acima_do_limite` |
| Aprovar pendência vencida ou de autor suspenso | `test_pj_regras_bancarias.py::test_pendencia_vence`, `test_pendencia_de_quem_foi_suspenso_nao_executa` |
| Fracionar e lote acima da alçada diária | `test_pj_regras_bancarias.py::test_fracionar_nao_dribla_a_alcada`, `test_lote_nao_dribla_a_alcada` |
| Enumerar login/recuperação (status, mensagem, campos e tamanho do token) | `test_forca_bruta.py::test_login_inexistente_e_senha_errada_respondem_igual`; `test_senha.py::test_recuperacao_nao_revela_se_a_conta_existe` |
| Contornar limites de cadastro/refresh/recuperação/Pix | `test_forca_bruta.py::test_cadastro_tem_limite_por_ip`, `test_refresh_tem_limite_por_ip`; `test_senha.py::test_recuperacao_tem_limite_por_conta`; `test_pj.py::test_consulta_de_chave_tem_limite` |
| Diferenciar qual dado cadastral já existe | `test_forca_bruta.py::test_cadastro_nao_diz_qual_dado_ja_existe` — mesma mensagem para duplicidade CPF/e-mail |
| Stack/credencial/valor inválido refletido em erro; CORS malicioso | `test_seguranca_api.py::test_erro_interno_nao_vaza_detalhe`, `test_validacao_nao_ecoa_o_valor_enviado`, `test_cors_nao_libera_origem_estranha_nem_credenciais` |
| Depósito demo sem habilitação | `test_deposito_demo.py::test_deposito_demo_desligado_por_padrao` |

Frontend: `auth-adversarial.test.tsx` verifica cache/estado/storage em quatro transições; `sessao.test.ts` verifica saída imediata, persistência só em memória, respostas tardias, refresh, falha temporária e 401 biométrico; `contestacao-estorno.test.tsx` testa três payloads XSS na tela real. Testes de CSP em `cabecalhos.test.ts` também passaram.

## Limites e pendências explícitos

- `npm audit --omit=dev` foi tentado e falhou por acesso ao registry; o resultado antigo de zero em SECURITY_AUDIT.md não foi apresentado como resultado atual. Nenhuma dependência foi instalada/atualizada.
- API local via TestClient/SQLite, biometria stub. DPoP obrigatório é exercitado pelos testes existentes dedicados; os helpers de fluxo deixam DPoP desligado. Não se testou resistência biométrica física, atestação/pinning em aparelho nem infraestrutura publicada.
- Nove testes foram pulados por requisitos do ambiente, incluindo concorrência em Postgres. Não há nova prova de concorrência financeira aqui.
- Mass assignment foi atacado nos fluxos financeiros/de acesso/cadastro citados, e os esquemas de entrada foram revisados. Não foi criada uma combinação exaustiva de todos os campos extras em cada POST/PATCH administrativo, de documentos e de autenticação.
- Catálogos de produto/voo são compartilhados por desenho, não objetos privados de outro titular. Admin foi atacado com usuário comum; não se obteve sessão administrativa real de produção.
- Cadastro novo 201 versus duplicado 409 ainda distingue disponibilidade do identificador; o teste existente apenas esconde qual dado duplicou. Pix existente 200 versus inexistente 404 também distingue chave, por finalidade de consulta, com limite e mascaramento. Esses comportamentos são preexistentes; não foram chamados de proteção integral contra enumeração.
- Recuperação tem diferença temporal residual já documentada; não foi feito benchmark estatístico. A neutralidade de campos/status/mensagem é a evidência automatizada citada.
- `/docs` e `/openapi.json` são habilitados no desenvolvimento. A configuração desliga ambos por padrão em produção (`settings.docs_ligados`, constructor de FastAPI); não foi consultado um deployment de produção para comprovar sua configuração.
- C1-04 requer revisão da retenção/redação de logs na infraestrutura; sem evidência de retenção indevida local. O contrato atual da rota exige a chave no caminho.

## Verificação

- Backend: ` .venv/Scripts/python.exe -m pytest -q -p no:warnings -o addopts=''`: **358 passaram, 9 pulados, 2 xfail strict**. `-o addopts=''` apenas evita o segundo `-q` do projeto para mostrar a contagem.
- App: `npx.cmd vitest run`: **109 passaram, 2 pulados**.
- `npx.cmd tsc --noEmit -p .`: passou.
- ESLint dos arquivos alterados, com a regra de formatação desligada conforme GPT.md: nenhum erro; um aviso preexistente de Fast Refresh em auth.tsx.
- Build development passou; build padrão recusou corretamente ausência de API. Audit indisponível, como acima.
- Arquivos editados exclusivamente via apply_patch; UTF-8 sem BOM e LF. Prettier foi aplicado por patch gerado a partir da saída do formatter, sem usar gravação direta. Nenhum git add/commit.
