# PayFlow — Mapa de telas (v1, 29/09/2026)

Base visual: design **"PayFlow 1f Fluxo Mono"** (salvo em `docs/design/v1-fluxo-mono-2026-09-28/`).
Legenda da coluna API: ✅ já existe · 🆕 precisa criar no backend · 🎨 só demonstração visual (dados fictícios)

## Regras de biometria facial (decisão da equipe)
| Momento | Facial? |
|---|---|
| Criar conta | **Sim, sempre** (cadastra o rosto) |
| Login | **Sim, sempre** |
| Transferência **até** o limite | **Não** (autorizada pela sessão do login) |
| Transferência **acima** do limite | **Sim**, selfie na hora |

- **Limite: R$ 500,00, configurável** (decidido). Fica numa variável de configuração (ex.: `LIMITE_FACIAL=500` no `.env`), nunca fixo no código.
- ⚠️ Transferir sem facial só é seguro **porque o login gera uma sessão (token)**. Sem login com token, qualquer pessoa poderia transferir valores baixos de qualquer carteira informando só o ID. Por isso login + token é pré-requisito dessa regra.

## Fluxo geral
```
Landing ──► Criar conta ──► Selfie de cadastro ──► Home
   │
   └──► Entrar (login) ──► Selfie de login ──► Home

Home ──► Transferir ──► Revisar pagamento ──┬─ valor ≤ limite ──► Transferência enviada ──► Home
  │                                         └─ valor > limite ──► Selfie de confirmação ──► Transferência enviada
  ├──► Extrato
  ├──► Contas
  └──► Painel do Governo 🎨
```

## Telas
| # | Tela | O que mostra / faz | API |
|---|---|---|---|
| 1 | **Landing** | Nome, slogan "Pagamentos que já chegam com o imposto certo", botões *Abrir minha conta* e *Entrar* | — |
| 2 | **Criar conta** | Nome, CPF, e-mail, telefone, senha (os três servem de login) | 🆕 hoje o cadastro recebe `carteira_id` + `saldo_inicial` escolhidos pelo usuário — rever |
| 3 | **Selfie de cadastro** 🆕 tela nova | Câmera frontal, moldura do rosto, dicas (luz, de frente, sem óculos escuros), estado "verificando…", erros (nenhum rosto, 2 rostos, liveness falhou) | ✅ `POST /usuarios` (`foto_rosto_base64`) |
| 4 | **Entrar (login)** 🆕 tela nova | Um campo único "CPF, e-mail ou telefone" (o sistema detecta qual é) + senha | 🆕 `POST /auth/login` (não existe) |
| 5 | **Selfie de login** 🆕 tela nova | Mesma câmera da tela 3 | 🆕 verificação facial no login → devolve token de sessão |
| 6 | **Home** | Saldo, atalhos Transferir/Extrato, transações recentes | ✅ `GET /usuarios/{id}` · ✅ `GET /pagamentos/transacoes` (🆕 filtrar só as do usuário) |
| 7 | **Transferir** | Para quem, valor, prévia do split (bruto → IBS/CBS → líquido) | Split 🎨 (motor não existe) |
| 8 | **Revisar pagamento** 🆕 tela nova | Resumo + aviso "acima de R$ 500 pedimos uma selfie" quando for o caso | — |
| 9 | **Selfie de confirmação** 🆕 tela nova | Mesma câmera; só aparece acima do limite | ✅ `POST /pagamentos/transferir` (🆕 foto opcional abaixo do limite) |
| 10 | **Transferência enviada** | Confirmação, valores, *Concluir* / *Nova transferência* | ✅ resposta do `/transferir` |
| 11 | **Extrato** | Lista com filtros | ✅ `GET /pagamentos/transacoes` (🆕 filtros e só do usuário) |
| 12 | **Contas** | Contas/destinatários salvos, botão *Usar* | 🎨 (hoje `GET /usuarios` lista todo mundo — não usar em produção) |
| 13 | **Painel do Governo** | IBS/CBS acumulado por empresa | 🎨 |

## Componente reutilizável: Câmera/Selfie
Usado nas telas 3, 5 e 9 — fazer **um componente só**. Estados: pedindo permissão · câmera aberta · foto tirada (refazer/usar) · verificando (~3–6 s, mostrar carregamento) · sucesso · erro com mensagem amigável.
Mensagens de erro para o usuário devem ser genéricas ("Não conseguimos confirmar seu rosto, tente de novo com mais luz") — sem mostrar distância/limite técnico.

## Mudanças de backend que essas telas pedem
1. `POST /auth/login` com identificador (CPF, e-mail **ou** telefone) + senha + selfie → token (JWT) de sessão. Os três campos precisam ser únicos no banco (`UNIQUE`).
2. Rotas protegidas pelo token (saldo, extrato, transferir só da própria carteira).
3. `POST /pagamentos/transferir`: `foto_verificacao_base64` opcional quando `valor ≤ LIMITE_FACIAL`; obrigatória acima.
4. Transações filtradas pelo usuário logado.
5. Cadastro sem `saldo_inicial` livre (saldo só por depósito — ou manter só na demo, sinalizado).

## Decisões tomadas (29/09/2026)
- [x] Limite para exigir facial: **R$ 500,00, configurável**
- [x] Login por **CPF, e-mail ou telefone** (campo único)
- [x] **Manter** o botão "Entrar como Alice (demo)" na apresentação (conta de demonstração com dados fictícios)
