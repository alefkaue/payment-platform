# 00 — Mapa de rotas e navegação (base neutra)

> Base **neutra**. Rotas reais do app (`app/src/routes/`) e superfície da API (`backend/app/routers/`) no commit `289effb`. Associação tela↔perfil↔endpoint marcada "a confirmar" onde não lida em profundidade nesta fase.

## Telas do app (TanStack file-based; `_app.*` = dentro do layout logado)

| Rota | Tela | Perfil principal | Observação |
|---|---|---|---|
| `/` | `index.tsx` | — | redirecionamento inicial |
| `/bem-vindo` | `bem-vindo.tsx` | público | onboarding |
| `/criar-conta` | `criar-conta.tsx` | PF/PJ | cadastro + captura facial |
| `/login` | `login.tsx` | PF | login (CPF/email/telefone + senha + rosto) |
| `/recuperar-senha` | `recuperar-senha.tsx` | PF | recuperação |
| `/inicio` | `_app.inicio.tsx` | PF/PJ | home (varia por conta) |
| `/pix` | `_app.pix.tsx` | PF/PJ | Pix / chaves |
| `/transferir` | `_app.transferir.tsx` | PF/PJ | transferência |
| `/depositar` | `_app.depositar.tsx` | PF/PJ | depósito demo |
| `/split` | `_app.split.tsx` | PJ | simulador de split |
| `/contas` | `_app.contas.tsx` | PF/PJ | seletor/gestão de contas |
| `/equipe` | `_app.equipe.tsx` | PJ | vínculos, papéis, alçadas |
| `/convites` | `_app.convites.tsx` | PJ | convite por CPF |
| `/pendentes` | `_app.pendentes.tsx` | PJ | aprovações maker-checker |
| `/folha` | `_app.folha.tsx` | PJ | folha de pagamento |
| `/extrato` | `_app.extrato.tsx` | PF/PJ | histórico |
| `/comprovante/$id` | `_app.comprovante.$id.tsx` | PF/PJ | comprovante |
| `/auditoria` | `_app.auditoria.tsx` | PJ | trilha de auditoria |
| `/cartoes` | `_app.cartoes.tsx` | PF | cartões (estado a confirmar) |
| `/seguranca` | `_app.seguranca.tsx` | PF/PJ | dispositivos, limites |
| `/config` | `_app.config.tsx` | PF/PJ | configurações |
| `/notificacoes` | `_app.notificacoes.tsx` | PF/PJ | avisos |
| `/perfil` | `_app.perfil.tsx` | PF/PJ | perfil |
| `/ajuda` | `_app.ajuda.tsx` | PF/PJ | suporte |

## Superfície da API por domínio (prefixos)
- **/auth** — login, login/mfa, login/totp, login/mfa/desafio, refresh, senha, recuperacao(/concluir), logout, eu, sessoes(/{id}, /encerrar-outras)
- **/contas, /empresas, /usuarios** — usuarios(/cadastro-sessao), contas(/atual), empresas(/atual: politica, documentos, vinculos(/{id}, /suspender))
- **/identidade** — kyc, documentos
- **/biometria** — (desafios/verificação — detalhar na Fase 1)
- **/pagamentos** — transferir, lote, transacoes(/{id}, /devolver, /contestar), pendentes/{id}/decidir, split/simular, split/transicao, depositar-demo
- **/cobrancas** — cobrancas(/{txid}: pagar, cancelar, estornar), pix-automatico/autorizacoes(/{id}: aceitar, recusar, cancelar, cobrancas)
- **/beneficios** — loja/produtos(/{id}/comprar), viagens/voos(/{id}: comprar, resgatar), pontos
- **/seguranca** — seguranca/limites, seguranca/dispositivos(/atual/confiar, /{id}: bloquear/desbloquear), seguranca/atividade, empresas/atual/auditoria, pix/chaves(/{id}), pix/consultar/{chave}, empresas/atual/(tributos, creditos, webhooks(/entregas)), rendimento
- **/admin** — (tarefas internas — detalhar na Fase 1)

## Autorização (pontos de controle — `deps.py`)
`usuario_atual` (sessão/JWT), `admin_atual`, `conta_atual` (resolve `X-Conta` → vínculo/papel/alçada), `exigir_papel`, `exigir_pj`, `dispositivo_atual` (DPoP/atestação), `chave_idempotencia`.

## A confirmar na Fase 1
- Associação exata tela→endpoint de cada `_app.*`.
- Telas sem endpoint correspondente (potenciais "vazias"/mock): verificar `cartoes`, `folha`, `notificacoes`, `rendimento`.
- Diferença de home PF × PJ e navegação (menu inferior / "Mais").
- Quais endpoints de `/beneficios` e `/admin` estão ativos vs desabilitados por flag.
