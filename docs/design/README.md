# Design do front-end — PayFlow

Protótipos do front feitos no **Claude Design** + o mapa de telas combinado pela equipe.
Nada aqui mexe no backend nem no `frontend/index.html` atual — é referência visual e de fluxo.

## Onde ver

| Versão | Arquivo | Claude Design (precisa de acesso ao projeto) |
|---|---|---|
| v1 · Fluxo Mono (escolhida) | `v1-fluxo-mono-2026-09-28/PayFlow 1f Fluxo Mono.dc.html` | [abrir](https://claude.ai/design/p/4c53e7b8-3387-4cb3-9af4-42c3cacc3591?file=PayFlow+1f+Fluxo+Mono.dc.html) |
| v2 · + Biometria | `v2-biometria-2026-09-29/PayFlow 1g Fluxo Mono + Biometria.dc.html` | [abrir](https://claude.ai/design/p/4c53e7b8-3387-4cb3-9af4-42c3cacc3591?file=PayFlow+1g+Fluxo+Mono+%2B+Biometria.dc.html) |
| v3 · Site (página web) | `v3-site-2026-09-29/PayFlow Site.dc.html` | [abrir](https://claude.ai/design/p/4c53e7b8-3387-4cb3-9af4-42c3cacc3591?file=PayFlow+Site.dc.html) |

**Sem acesso ao Claude Design?** Os arquivos abrem direto no navegador: clone o repo e dê duplo clique no `.dc.html`
(o `support.js` ao lado é o runtime do protótipo e precisa ficar na mesma pasta). Precisa de internet por causa das fontes.
Se o navegador bloquear arquivo local, rode `python -m http.server` dentro da pasta e abra `http://localhost:8000`.

## Estilo "Fluxo Mono"
- Monocromático (preto `#141414` / off-white `#fbfaf7`), imposto destacado em **ocre**; tema claro e escuro.
- Fontes: **Instrument Sans** (texto) + **JetBrains Mono** (valores/códigos). Cantos 14–22px.
- Todas as cores são variáveis CSS (`.pf-light` / `.pf-dark` no topo do HTML) — fácil de levar pro front real.

## O que a v2 adiciona
- **Entrar**: escolhe CPF | E-mail | Telefone + senha → selfie. (Chave em vez de campo único porque CPF e celular têm 11 dígitos.)
- **Criar conta**: + e-mail, telefone, senha → selfie de cadastro.
- **Selfie**: um componente só (cadastro, login, pagamento) com estados pronto / verificando / confirmado / erro.
- **Revisar pagamento**: até o limite → "autorizado pela sessão"; acima → "confirmar com selfie".
- Comprovante e extrato mostram **"Autorizado por: Sessão / Selfie"**.
- Limite configurável (`limiteFacial`, padrão **R$ 500**) no painel Tweaks do Claude Design.
- Painel lateral "Selfie (demo) → Falha 1x" para demonstrar o estado de erro.

Split IBS/CBS, Contas e Painel do Governo são **só demonstração visual** por enquanto (backend ainda não tem o motor de split).

## Decisões da equipe
Ver [`mapa-de-telas.md`](mapa-de-telas.md): fluxo completo, cada tela ↔ rota da API, e decisões tomadas
(facial no cadastro e no login; na transferência só acima de R$ 500 configurável; login por CPF, e-mail ou telefone;
manter "Entrar como Alice (demo)").

## O que o backend precisa para esse fluxo funcionar
Hoje quem paga é o `origem_carteira_id` que o próprio cliente envia — por isso a selfie é obrigatória em toda transferência.
Para liberar valores baixos sem selfie com segurança:
1. `POST /auth/login` (identificador + senha + selfie) → **token JWT** com expiração curta. Senha guardada como hash (bcrypt/argon2).
2. Rotas protegidas pelo token; **a carteira de origem vem do token**, não do body. Saldo/extrato só do usuário logado.
3. `LIMITE_FACIAL` (variável de ambiente, padrão 500): `foto_verificacao_base64` obrigatória só acima dele.
4. Cadastro com CPF, e-mail e telefone **únicos** + `senha_hash`.
5. Limite de tentativas de login/selfie e mensagens de erro genéricas.

## Pontos de segurança observados no código atual (para discutir)
- `saldo_inicial` escolhido pelo cliente no cadastro (dá pra "criar dinheiro") — ok para demo, sinalizar na apresentação.
- `GET /usuarios` e `GET /pagamentos/transacoes` expõem nome/saldo/transações de todos, sem login.
- A mesma foto base64 pode ser reenviada (replay) — não há desafio/nonce que expire.
- O erro 401 da biometria devolve `distância` e `limite` — ajuda um atacante a ajustar fotos; melhor mensagem genérica + detalhe só no log.
- `sessoes_mfa` e `logs_auditoria` existem no schema mas nenhum código grava nelas (o README diz que `sessoes_mfa` registra as tentativas).
- `valor` aceita mais de 2 casas decimais: `0.001` passa em `> 0` e grava `0.00` — validar como Decimal com 2 casas.
