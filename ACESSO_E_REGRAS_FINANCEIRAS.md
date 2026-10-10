# Astro — autenticação, autorização e regras financeiras

Como o sistema decide **quem é você**, **o que pode fazer** e **quando o dinheiro sai**.
Os valores são os padrões de `backend/app/core/config.py` (variável de ambiente entre
parênteses). Inventário por rota: `ENDPOINTS.md`.

## 1. Autenticação

| Etapa | Regra |
|---|---|
| Cadastro | Nome, e-mail, CPF, senha, **rosto** (prova de vida de cadastro) e **documento frente e verso** (KYC). Resposta neutra (não diz qual dado já existe). 10 cadastros/h por IP (`CADASTRO_MAX_IP_HORA`) |
| Senha | Mínimo 10 (`SENHA_MIN`), máximo 128; recusa senhas comuns e com CPF/e-mail/nome; **sem** regra de composição (NIST 800-63B). Guardada em Argon2id (m=19 MiB, t=2, p=1) |
| Login, 1º fator | Senha + prova DPoP. Mensagem igual para e-mail inexistente e senha errada. 10 falhas por conta **a partir do mesmo IP** travam esse IP; 50 por conta somando IPs travam a conta; 30 por IP em geral; janela de 15 min |
| Login, 2º fator | Rosto com prova de vida (passos sorteados pelo servidor, desafio de uso único, 120 s), **no mesmo aparelho e com a mesma chave** do 1º fator. `mfa_token` vale 5 min. No APK: atestação da chave do Keystore (`ATESTACAO_EXIGIDA` opcional) |
| Sessão | Access token 15 min; refresh 7 dias com rotação; **teto de 12 h** e queda após **30 min** parado (`SESSAO_MAX_HORAS`, `SESSAO_INATIVIDADE_MIN`). Cada requisição confere se a sessão está ativa: encerrar sessão, logout ou bloquear aparelho derruba na hora |
| Tokens | JWT HS256 (algoritmo fixo), `iss`, `aud`, `exp`, `typ` e tipo exigidos; tokens **presos à chave do aparelho** (DPoP, RFC 9449): cada requisição leva uma prova assinada com método, caminho, horário (±60 s), id único e hash do token |
| Onde ficam no app | Na memória/`sessionStorage` (navegador) e WebView (APK). Não ficam em cookie, então não há CSRF; o CORS não libera credenciais. Copiar o token não basta: sem a chave não exportável do aparelho ele não serve |
| Admin da plataforma | Senha + código TOTP de uso único do app autenticador (`POST /auth/login/totp`, `ADMIN_TOTP_SEGREDO`). Em produção só entra de IPs em `ADMIN_IPS_PERMITIDOS`; sem a lista, fica desligado; com a lista, o TOTP é obrigatório |
| Troca de senha | Logado: senha atual + rosto; política de senha; encerra as outras sessões (`POST /auth/senha`) |
| Recuperação de senha | E-mail/CPF + data de nascimento, depois prova de vida completa no mesmo aparelho; resposta neutra; uso único; derruba todas as sessões; 10/h por IP e 5/h por conta (`/auth/recuperacao`) |

## 2. Autorização

- **Identidade** = token + prova DPoP + sessão ativa. Nada do corpo ou de header decide quem é você.
- **Conta em uso**: sem `X-Conta`, a carteira PF da pessoa; com `X-Conta`, uma empresa em que a pessoa tem **vínculo ativo** — conferido no servidor em toda requisição.
- **Objetos**: transação, chave Pix, sessão, aparelho, cobrança, pendência, vínculo, webhook, funcionário — sempre buscados **dentro** da conta/pessoa do token; de outro = 404.
- **Campos protegidos** (saldo, papel, status, dono, valores calculados) não existem nos esquemas de entrada; o que vier a mais é ignorado.

### Papéis numa empresa (PJ)

| Papel | Pode |
|---|---|
| `admin` | Tudo, inclusive gerir acessos. Sem alçada (exceto a assinatura conjunta da Grande) |
| `aprovador` | Movimentar e aprovar até a própria alçada |
| `operador` | Lançar; acima da alçada (ou da alçada diária) vira pendência |
| `consulta` | Ver saldo e extrato; nunca movimenta (o app também esconde as ações) |

### Por porte (`services/politica_pj.py`)

| | MEI | PME | Grande |
|---|---|---|---|
| Quem administra | Só o titular | Vários admins | Vários admins |
| Papéis convidáveis | operador, consulta | todos | todos |
| Operador sem alçada | não | pode | não |
| Dar poder (admin/aprovador, alçada maior, reativar) | — | rosto de quem concede | rosto **e** outro admin aprova (com ≥ 2 admins) |
| Assinatura conjunta | — | — | acima de R$ 250.000 (`LIMITE_DUAS_APROVACOES_REAIS`) |

## 3. Quando o dinheiro sai

Ordem das conferências numa transferência (`services/pagamento_service.py`):

1. Origem ≠ destino; papel que movimenta; aparelho informado.
2. **Precisa de outra pessoa?** (só PJ) — vira pendência se:
   - o valor passa da **alçada por operação** de quem lança;
   - a soma do dia de quem lança passaria da **alçada diária** (vazia = igual à alçada por operação). Conta o que a pessoa movimentou sozinha hoje (horário de Brasília); não conta o que foi executado por aprovação;
   - é empresa **Grande** e o valor ≥ limite de assinatura conjunta — **vale também para admin**.
3. **Rosto** acima de R$ 500 (`LIMITE_FACIAL_REAIS`).
4. **Risco**: destino novo a partir de R$ 1.000 → valor fica **retido** 72 h no recebedor (bloqueio cautelar).
5. **Dentro do lock da carteira**, junto com o débito: saldo, limite por transação, diurno/noturno (20h–6h), teto de aparelho novo (PF: R$ 200 por transação, R$ 1.000 por dia) e de novo a alçada diária.

Limites padrão por carteira: PF R$ 5.000 por transação / R$ 10.000 diurno / R$ 1.000 noturno;
PJ R$ 50.000 / R$ 200.000 / R$ 20.000. Aumento de limite só vale depois de 24 h; redução vale na hora.

### Pendência (maker-checker)

- Quantas aprovações: 1; na Grande acima do limite, 2. Se quem lançou é admin/aprovador
  com poder para aquele valor, ele conta como uma das assinaturas (falta 1). *Decisão
  tomada nesta auditoria; é o modelo de assinatura conjunta dos bancos empresariais.*
- Quem lançou **nunca** aprova; pode **cancelar** a própria.
- Quem aprova: admin ou aprovador, cada um uma vez, dentro da própria alçada, com rosto
  acima de R$ 500; mudanças de acesso só admin, sempre com rosto.
- Vence em 72 h (`PENDENTE_VALIDADE_HORAS`) → `expirada`.
- Se quem lançou foi suspenso ou revogado → `cancelada` em vez de executar.
- Ao completar as aprovações, executa com as mesmas conferências de saldo e limite;
  se falhar (ex.: sem saldo) → `falhou`, nada é debitado.

### Integridade

- Dinheiro em `Decimal` / `NUMERIC(14,2)`; entrada: positivo, até 2 casas, até 12 dígitos.
- Débito, crédito, histórico de saldo, split e baixa da cobrança na **mesma transação**
  do banco, com as carteiras travadas (`SELECT … FOR UPDATE`) em ordem fixa.
- **Idempotência**: `Idempotency-Key` por conta, única no banco. Repetir devolve a mesma
  transação; usar a mesma chave para outro valor ou destino → 409.
- Transação concluída não tem rota de edição: só **contestação** (MED, até 80 dias) e
  estorno de cobrança, ambos gerando transações novas ligadas à original.
- Split (Reforma Tributária): só no pagamento de cobrança com NF-e; CBS/IBS calculados
  no servidor a partir da nota, nunca do valor enviado pelo cliente.
