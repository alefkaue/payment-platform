# C2 — Revisão cruzada e idempotência por intenção

Data: 10/10/2026. Worktree `astro-gpt`. Lidos GPT.md, relatório C1, README.md, ACESSO_E_REGRAS_FINANCEIRAS.md, ENDPOINTS.md, docs/BANCO.md, app/AGENTS.md, SEGURANCA.md e SECURITY_AUDIT.md. Os nove hashes solicitados foram examinados com `git show`; os testes usam a implementação atual do worktree. Nenhuma alteração em backend/app, modelos, migrações ou testes anteriores. Sem git add/commit.

## Achados

| ID | Gravidade | Commit/arquivo | Evidência | Status |
|---|---|---|---|---|
| C2-01 | Alta | aaf3f71; backend/app/services/folha_service.py, `_chave_da_folha` | `test_adv_c2_financeiro.py::test_folha_valor_equivalente_nao_repete[300/3e2/300.0]`: salário cadastrado 300.00 e reenvio explícito equivalente creditam 600.00 | Confirmado; 3 xfail strict; corrigir no backend |
| C2-02 | Alta | abed40a; backend/app/repositories/extras.py, `transacoes_da_pendente` | `test_conciliar_chave_publica_nao_prova_execucao`: Pix público de R$ 1 com chave `pendente-{id}` faz conciliar como aprovada pendência de R$ 3.000 que caiu antes de executar | Confirmado; xfail strict; corrigir no backend |
| C2-03 | Baixa | 96a618a; backend/app/deps.py, `chave_idempotencia` | `test_header_vazio_nao_executa[   ]`: espaços são convertidos em None; Pix de R$ 10 executa com 200 sem chave. Header literalmente vazio retorna 422 | Confirmado; xfail strict; corrigir validação no backend |
| C2-04 | Média | 96a618a/7903369; backend/app/services/cobranca_service.py, `pagar` | `test_cobranca_reenvio_header_retorna_mesmo_pagamento`: mesma chave, primeiro POST 200, reenvio 409 antes de consultar idempotência | Confirmado; xfail strict; dinheiro permanece único, mas resposta não recupera sucesso |
| C2-05 | Média | aaf3f71/96a618a; serviços pagamento, cobrança e folha | `test_reenvio_pendente_mesma_chave_nao_duplica[pix/folha/cobranca]`: mesma chave cria ids distintos de pendência; campo `_entregas` não aparece | Confirmado; 3 xfail strict; risco de aprovar duas intenções equivalentes |
| C2-06 | Alta | app/src/lib/api.ts e telas transferir/folha | `idempotencia-c2.test.tsx` e `idempotencia-api-c2.test.ts`: chave por tentativa era renovada no Pix, ausente na folha | Corrigido no app; 7 testes novos passando |

Os achados iniciais foram executados sem marcador; os casos foram também executados com `--runxfail`, desativando a marcação para confirmar as falhas pelo comportamento descrito. Os três cenários de pendência foram corrigidos depois de esse comando detectar um erro no fixture; a nova execução sem marcação mostrou ids 2 e 3 nos três fluxos, na assertiva esperada. Todos os marcadores restringem a falha esperada a `AssertionError`, para não mascarar erros de montagem do teste. `strict=True` fará uma correção futura produzir XPASS e exigir a remoção do marcador. Eles não tornam a vulnerabilidade resolvida.

### C2-01 — reprodução e alcance

Empresa com saldo, funcionário cadastrado com salário 300.00. Primeiro POST de folha envia só funcionario_id; segundo envia o mesmo funcionário e valor `300`, `3e2` ou `300.0`, sem chave explícita. Ambos respondem 200 e o funcionário termina com 600.00. O hash usa a representação textual de Decimal, não seu valor normalizado. Ordem dos itens e espaços/capitalização do rótulo já têm normalização, mas dinheiro não.

Recomendação: normalizar os valores em duas casas antes de derivar a chave. A alternativa de chave explícita usada agora pelo app evita esse vetor enquanto a intenção permanece a mesma. Não elimina o problema de outros consumidores sem chave.

### C2-02 — reprodução e alcance

O fixture cria pendência real de R$ 3.000 com operador sujeito à alçada. O admin faz um Pix separado de R$ 1 para outro destino, enviando chave pública `pendente-{id}`. Durante a aprovação real, o teste simula queda de processo na entrada de `pagamento_service.transferir`, antes do movimento; não injeta aprovação por SQL. Depois de 11 minutos, o job encontra a transação de R$ 1 pela chave e declara a pendência aprovada. A carteira perdeu apenas R$ 1; o pagamento solicitado nunca aconteceu.

Recomendação: vincular transações à operação por referência interna persistida e conferir tipo, destino, valor e itens. Apenas reservar prefixos limita o ataque, mas não prova a execução. Não houve confusão entre empresas no teste dedicado; o teste existente de pendente-1 versus pendente-12 também passou. O achado é sobre procedência do movimento encontrado, não sobre o LIKE isoladamente.

### C2-03, C2-04 e C2-05 — contratos de reenvio

Espaços no header passam a validação de tamanho e são descartados. O cliente que acredita ter fornecido uma chave pode reenviar e pagar outra vez. Sem header, o contrato continua admitindo operações sem idempotência; o problema demonstrado é aceitar header informado e inválido silenciosamente.

Cobrança já paga não duplica dinheiro: a barreira de status impede. Porém, após perda da resposta 200, o reenvio com a mesma chave vira erro 409 e o app não recebe o comprovante. Recomenda-se retornar a transação original quando a chave pertence à mesma conta e à mesma cobrança, preservando autorização e conflito com outro pedido.

Nos três fluxos sujeitos à aprovação, a criação de pendência antecede o tratamento idempotente. Os testes confirmam ids distintos com a mesma chave. Não foi afirmado débito automático imediato: os dois pedidos ainda precisam de aprovação. A nova chave estável do app não consegue impedir a duplicação de pendências enquanto o servidor a ignora nessa etapa.

## Revisão por commit — o que tentei / resultado

### f9f806c — troca e recuperação de senha

**O que tentei:** aliases e-mail maiúsculo/com espaços, CPF puro/pontuado e X-Forwarded-For forjado; limite por IP com contas inexistentes diferentes; JWT com assinatura forjada, campo cifrado adulterado com assinatura de teste válida e expiração passada; concluir de outro aparelho; recuperar admin; reutilizar token com desafio novo; access e refresh de outra sessão após recuperação. Testes novos em `test_adv_c2_auth.py`. Os testes existentes de troca, enumeração, rosto recusado e sessões foram executados na suíte completa.

**Resultado:** aliases convergem para o mesmo limite; IP forjado não o contorna; 429 nos limites; tokens/aparelho/admin recusados com 401; senha não muda nos ataques. Recuperação válida derruba access de ambas as sessões e refresh do notebook. Reuso continua recusado. Enumeração por status, campos e tamanho passa nos testes existentes. Expiração é verificada por claim assinada; não se aguardou dez minutos reais. Diferença temporal residual não foi medida estatisticamente; não declaro neutralidade temporal. Os testes são com biometria stub e não avaliam resistência física do rosto.

### 0f2fd21 — TOTP do admin

**O que tentei:** relógio do verificador controlado; código de dois passos atrás; código de um passo à frente; reaproveitar esse código em outro token; brute force reaproveitando o mesmo token; produção com admin ligado e segredo ausente. Executados também os vetores RFC, formatos ruins, troca rosto/TOTP nos dois sentidos e reuso dos testes existentes.

**Resultado:** fora da janela retorna 401; passo +1 é aceito pela janela deliberada; código usado em outro token retorna 401; erros no mesmo token contam e chegam a 429. A configuração real de produção rejeita o boot sem ADMIN_TOTP_SEGREDO quando o admin está ligado. Um experimento que alterava Settings depois do boot aceitava login sem segredo; foi descartado como prova de falha porque burlava artificialmente a validação de startup. O teste entregue exercita a configuração real, sem esse estado impossível por ambiente. Nenhuma falha adicional confirmada.

### abed40a — conciliação de executando

**O que tentei:** transação pública com chave reservada, outro valor/destino; transação de outra empresa com mesma chave; executar job após queda antes/depois do dinheiro; pendente-1 versus pendente-12; reexecução do job e janela de dez minutos.

**Resultado:** C2-02 confirmado. A empresa diferente não contamina a conciliação. Testes existentes de prefixo, janela, controle administrativo e reexecução passam. Uma folha parcialmente executada é marcada aprovada com contagem de itens executados pelo desenho atual; isso foi observado na leitura, sem novo achado automatizado independente. Não alego que esse status represente pagamento integral de todos os itens.

### 7903369 — outbox Pix/cobrança

**O que tentei:** repetir Pix com chave; consultar respostas/listagens buscando `_entregas`; falhar `_enfileirar_webhooks` na rota real; derrubar a entrega imediata após commit e reenviar; rodar o job duas vezes; pagamento sem saldo e repetição de cobrança dos testes existentes.

**Resultado:** falha do outbox desfaz débito e crédito; queda depois do commit mantém saldo movimentado e entrega pendente; reenvio não duplica transação/evento e o segundo job processa zero. Não apareceu `_entregas` nas respostas pesquisadas. C2-04 permanece como falha de resposta idempotente, com um único débito/evento. Isso não prova entrega externa exatamente uma vez: retries após timeout e workers simultâneos podem exigir deduplicação no consumidor por entrega_id. Não houve teste de concorrência de entrega HTTP externa.

### 32b59a4 — outbox estorno/pendência

**O que tentei:** falhar a gravação do evento durante estorno e durante criação de pendência no repositório real; procurar `_entregas` nas três respostas de pendência e na resposta de estorno existente; repetir estorno nos testes existentes.

**Resultado:** estorno falho deixa cobrança paga, pagador com 90.00 e recebedor com 10.00; criação falha não deixa pendência. Ambos preservam apenas o evento prévio de cobrança paga. Respostas testadas não expõem o campo interno. A pendência existente no fixture C2-05 não tinha webhook inscrito; a atomicidade da gravação foi isolada diretamente no repositório e é independente da inscrição.

### aaf3f71 — idempotência da folha

**O que tentei:** mudar só representação de valor; espaços no rótulo; mesma chave em outra empresa; reordenar itens, outra competência/outro valor e chave explícita nos testes existentes; reenvio que cria aprovação.

**Resultado:** C2-01 e a parte folha de C2-05 confirmados. Espaços externos no rótulo e reordenação não duplicam. Mesma chave em duas empresas paga cada folha uma vez, sem colisão. Outro mês, descrição de adiantamento ou valor continua permitido pelos testes existentes. Sem chave explícita, mesmo conjunto/valor/rótulo no mesmo mês é deliberadamente tratado como reenvio; um segundo pagamento legítimo indistinguível precisa de descrição/competência distinta ou nova chave explícita. Não foi classificado como falha por falta de identificador de negócio que distinga essas intenções.

### 34f2a90 — teto agregado de aparelho novo

**O que tentei:** omitir header em sessão criada sem dispositivo; movimentar de aparelho bloqueado; PJ com aparelho não confiável; alternar aparelhos PF no teste existente.

**Resultado:** sem header a rota financeira retorna 400 antes de movimentar; aparelho bloqueado retorna 401. Trocar aparelhos PF não renova o teto de 1.000 no teste existente. PJ pode enviar 300 com dispositivo não confiável porque o teto reduzido é explicitamente PF; não tratei a regra de produto como contorno. Não foi demonstrado contorno do teto agregado.

### d975d83 — Pix Automático e NF-e única

**O que tentei:** duas autorizações de empresas diferentes somando saídas do mesmo PF acima do diurno de 150; campo parcelas extra na rota recorrente; limite por transação do teste existente; nota com duas parcelas, cancelar uma e tentar reemitir, cancelar ambas e reemitir; usar nota de outra empresa.

**Resultado:** duas cobranças de 90 pagam só uma; saldo final 910 e a segunda falha por limite. A rota recorrente não aceita parcelamento: campo extra não altera o valor e parcelas_total permanece 1 pelo contrato. NF-e não permite reemissão enquanto há uma parcela aberta; depois de cancelar todas, permite. Nota de outro CNPJ retorna 400 antes de gravar. SQLite não prova serialização de duas emissões concorrentes; os testes Postgres continuam pulados no ambiente.

### 96a618a — Idempotency-Key no header

**O que tentei:** vazio/espaços; mesmo header reenvio de cobrança; header numa rota GET sem suporte; conflito header/corpo e Pix de valor diferente nos testes existentes; folha com header e descrição diferente no teste existente.

**Resultado:** vazio 422, espaços aceitos sem proteção (C2-03). Conflito retorna 400; Pix retorna a mesma transação ou 409 para valor diferente; folha com chave explícita não duplica. GET /contas/atual ignora o header sem prometer efeito financeiro. C2-04 e C2-05 mostram limites de suporte nas rotas anunciadas: cobrança já paga e aprovação não recuperam a intenção pela chave.

## Correção do app

`criarIntencaoPagamento` guarda assinatura e chave na instância da tela, usando crypto.randomUUID quando disponível e getRandomValues como fallback. Não contém identidade pessoal, timestamp ou dinheiro na chave.

Transferir gera a chave após consultar o destino e montar a revisão; assinatura inclui conta de origem, destino resolvido e valor. Voltar e revisar os mesmos dados conserva a chave. Mudança de destino/valor ou sucesso confirmado cria uma intenção nova. A troca de conta remonta o formulário. api.ts recebe e envia a chave, sem criá-la a cada tentativa. Falha inclusive na consulta da conta após o POST não conclui a intenção.

Não existia função/tela de pagar cobrança no app atual: foi acrescentada a opção de cobrança por txid na mesma tela de pagamento, consultando o valor antes da revisão, com função API que envia a chave e rosto. O servidor calcula os impostos e autoriza o pagamento. Esse fluxo depende da API; não foi criado um motor de pagamento de cobrança demo.

Folha guarda a chave ao preparar a confirmação, pela conta e conjunto de funcionários/valores normalizados. Nova tentativa conserva a chave mesmo que o rosto ou a descrição mude. Ao receber pendência ou todos os itens pagos, limpa seleção e encerra a intenção. Resultado parcial conserva seleção e chave para repetir sem pagar de novo os itens já concluídos; alterar itens/valores passa a ser intenção nova. Uma intenção modificada após sucesso parcial pode incluir salários já pagos: o usuário deve revisar os itens; não foi criado mecanismo de estorno/correção de folha.

Testes de telas reais simulam erro de rede e verificam as chaves fornecidas ao API; testes da camada API inspecionam os corpos entregues ao cliente HTTP para os três tipos. Cobrem troca de valor, troca de destino, próxima operação após sucesso e fallback criptográfico. Persistência após recarregar/fechar a tela não faz parte do cartão: a chave vive enquanto a intenção está montada. Os achados C2-04/05 impedem prometer recuperação transparente de todo sucesso perdido no backend, embora o app agora reenvie a chave correta.

## Verificação e limites

- App completo: 117 passaram, 2 pulados; TypeScript e ESLint dos seis arquivos alterados passaram.
- Backend completo: 396 passaram, 9 pulados, 9 xfail strict; testes C2 isolados incluem 25 passando e 9 xfail strict.
- Prettier aplicado por patches gerados do formatter, sem gravação direta; arquivos editados via apply_patch, UTF-8 sem BOM, LF. git diff --check passou.
- SQLite em memória, biometria stub. Configuração de produção testada sem deployment; provas DPoP dedicadas existentes executadas na suíte. Não se mediu tempo de recuperação estatisticamente nem entrega HTTP concorrente. Não foram instaladas dependências.

## Como reproduzir

Backend: `cd backend; .venv/Scripts/python.exe -m pytest -q -p no:warnings tests/test_adv_c2_auth.py tests/test_adv_c2_financeiro.py -o addopts=''`. Para ver as assertivas reais dos achados: acrescentar `--runxfail`, esperando nove falhas (não é comando de aceite).

App: `cd app; npx tsc --noEmit -p .; npx vitest run`. Manualmente, revisar Pix, interceptar a resposta do POST como falha de rede e confirmar novamente: comparar idempotency_key dos dois pedidos. Voltar, mudar valor/destino e revisar: chave diferente. Completar e iniciar outra operação igual: chave diferente. Repetir com folha; cobrança fica na opção por txid e tem a limitação 409 descrita em C2-04.
