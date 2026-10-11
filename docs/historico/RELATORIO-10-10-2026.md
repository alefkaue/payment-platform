# Relatório do trabalho — 10/10/2026

Resumo de tudo o que entrou no repositório nesta rodada, depois da apresentação de 09/10.
O foco foi preparar o Astro para o **pentest dos outros grupos**: infraestrutura, app
nativo, auditoria de segurança completa e a correção da verificação facial.

Detalhe técnico de cada ponto:

| Documento | Conteúdo |
|---|---|
| `SECURITY_AUDIT.md` | Cada vulnerabilidade: gravidade, evidência, correção, teste, pendências e ações manuais de nuvem |
| `THREAT_MODEL.md` | Ativos, atores, fronteiras de confiança, ameaças e riscos residuais |
| `ACESSO_E_REGRAS_FINANCEIRAS.md` | Login, papéis, alçadas e quando o dinheiro sai |
| `ENDPOINTS.md` | As 101 rotas da API e quem pode chamar cada uma (gerado do código) |
| `SECURITY.md` | Como reportar falhas e como rodar os testes de segurança |
| `PENTEST.md` | Regras do pentest para os outros grupos |
| `AZURE.md` | Passo a passo do ambiente na Azure |
| `SEGURANCA.md` | Histórico dos itens de segurança 1–10 e diário |

---

## 1. Commits desta rodada

| Commit | O quê |
|---|---|
| `8eb9ded` | Segurança 7: sessão que cai volta ao login com o motivo; build de produção recusa modo demonstração; CSP no host |
| `0882ec8` | Segurança 8: segredos só do ambiente; CORS sem curinga; produção conferida no boot |
| `dc8e48e` | Segurança 9: infraestrutura do pentest na Azure, Dockerfile de produção endurecido, `PENTEST.md` |
| `3c6f32d` | Segurança 10: chave do aparelho no Keystore com atestação, certificate pinning, APK endurecido |
| `eeefdd1` | Auditoria completa: regras PJ, SSRF, dependências, testes e documentação |
| `13db672` | Cadastro: documento opcional só no servidor de desenvolvimento (para testar sem documento) |
| `e595d0c` | Prova de vida: as piscadas que o app vê agora chegam ao servidor |

## 2. Infraestrutura para o pentest (item 9)

- `infra/azure/main.bicep`: API no Container Apps dentro de uma rede privada; Postgres
  **sem acesso público**; segredos só no Key Vault, lidos por identidade gerenciada;
  Front Door com WAF limitando requisições por IP; app web no Static Web Apps com CSP.
  Compila e passa no lint do Bicep. **Não foi implantado** (precisa da conta Azure).
- `.github/workflows/azure.yml`: deploy contínuo com login **OIDC** (nenhuma senha no GitHub).
  Só roda depois que as variáveis do repositório forem configuradas.
- `backend/Dockerfile`: usuário sem privilégio, código e modelos de biometria só leitura,
  modelos conferidos por SHA-256 no build, OCR em português, modo produção.
- A API passou a reconhecer o IP real do cliente atrás do Front Door e do proxy.
- `PENTEST.md`: escopo, regras (sem DoS, só contas próprias), contas de teste, como
  testar a API direto, o que já se sabe e modelo de relatório.

## 3. App nativo Android (item 10)

- A chave que assina cada requisição (DPoP) fica no **Android Keystore**, em hardware;
  nem o próprio app consegue ler a chave, só pedir assinaturas.
- **Atestação**: o Android entrega um certificado, assinado pela Google, provando que a
  chave está em hardware de verdade, no nosso app, num aparelho com sistema original.
  O backend confere no login (substitui o Play Integrity, que exigiria Play Store).
- **Certificate pinning** da API, gerado no build a partir da cadeia real do servidor.
- APK sem backup, com bloqueio de print e gravação de tela, WebView sem depuração;
  APK release assinado com chave fixa quando os secrets existirem.
- **Ainda não testado num celular.**

## 4. Auditoria de segurança

Feita rota por rota, com testes que **tentam o ataque** antes de afirmar qualquer coisa.

### Problemas encontrados e corrigidos

| Gravidade | Problema | Correção |
|---|---|---|
| Alta | Na empresa **Grande**, o admin pagava sozinho valores acima do limite de dupla aprovação | Acima do limite, ninguém paga sozinho; quem lança conta como uma das assinaturas se tiver poder para aquele valor |
| Alta | **Fracionamento**: com alçada de R$ 1.000, cinco Pix de R$ 900 passavam sem aprovação (o mesmo com lote) | Nova **alçada diária por pessoa**, conferida também dentro da trava do banco (pedidos simultâneos não furam) |
| Alta | Bibliotecas com vulnerabilidades conhecidas (PyJWT e Starlette) | Atualizadas: FastAPI 0.143, Starlette 1.7, PyJWT 2.15 |
| Média | **SSRF** nos webhooks: o servidor podia ser usado para chamar a rede interna | Só https público, portas 443/8443, DNS conferido na hora do envio |
| Média | Operação pendente nunca vencia e podia ser aprovada depois de quem a lançou ser suspenso | Vence em 72 h, quem lançou pode cancelar, autor sem acesso → cancelada |
| Média | Qualquer pessoa travava a conta de outra errando a senha 10 vezes | O bloqueio passou a ser por conta + IP; a conta só trava com 50 falhas de vários IPs |
| Média | O limite de tamanho da requisição era burlável | Limite vale para qualquer forma de envio |
| Baixa | Mesma chave de idempotência com outro valor devolvia a transação antiga | Responde 409 |
| Baixa | CPF do pagador visível a qualquer pessoa com o código da cobrança | Mascarado para quem não é parte |
| Baixa | Listagens sem limite de tamanho; front mostrando "Pagar" para quem só consulta; API exposta no docker-compose | Corrigidos |

### Conferido e correto (com teste)
- Ninguém acessa recurso de outra pessoa trocando o id na URL (19 rotas testadas).
- Nenhuma das ~90 rotas protegidas responde sem login.
- Campos protegidos (saldo, papel, status) enviados pelo cliente são ignorados.
- Valores negativos, zero, com 3 casas, `NaN` ou gigantes são recusados.
- Débito, crédito e histórico acontecem juntos numa única transação do banco.
- Sem SQL injection nem XSS nos fluxos testados; erros não mostram detalhes internos.
- Nenhum segredo real no código nem no histórico do git.

### Também entrou
- Logs em JSON com o código da requisição; falha ao gravar a auditoria não derruba um Pix.
- `.github/workflows/backend.yml`: roda os testes, os testes de **concorrência contra um
  Postgres de verdade**, as migrações e a checagem de dependências a cada push.

## 5. Verificação facial

Problema relatado: o app mostrava as piscadas, mas o servidor dizia "0 piscadas detectadas".

- **Causa 1**: o app só guardava os primeiros ~2 segundos de cada passo. Piscando
  devagar (como pedido), as piscadas ficavam de fora do que era enviado.
- **Causa 2**: o servidor media o olho com uma conta distorcida pelo formato da câmera.
- **Correção**: o app envia os quadros do olho fechado e reaberto de cada piscada (e,
  em sorrir/virar, os quadros da ação); o servidor usa o mesmo sinal do app.
  As proteções continuam: passos na ordem, ação não pedida reprova, piscar demais reprova.

## 5.1 O que o CI com Postgres pegou

No primeiro push, o novo CI rodou os testes num Postgres de verdade e falhou. Investigado
localmente com um Postgres embutido, apareceram dois bugs que o SQLite dos testes escondia:

- **Cadastro com documento quebrava em produção** (erro 500): frente + verso geram um
  código de 129 caracteres, e a coluna aceitava 64. Corrigido com uma migração que só
  aumenta a coluna.
- **Pix repetido ao mesmo tempo** (o app reenviando por rede ruim) dava erro 500 em vez de
  devolver o Pix original. O saldo nunca ficou errado. Corrigido.

O build do APK também falhava (já antes desta rodada): faltava o passo `cap sync`, que
gera arquivos do Capacitor que não ficam no git. Corrigido no workflow.

O CI agora roda **a suíte inteira no Postgres** e confere que as migrações batem com o código.

## 6. Números

| | Antes | Depois |
|---|---|---|
| Testes do backend | 203 | **250** no SQLite e **253** no Postgres (inclui concorrência) |
| Testes do app | 19 | 19 |
| Avisos de vulnerabilidade em dependências (`pip-audit`; o `npm audit` de produção já estava em 0) | 35 | **0** |

## 7. O que falta

1. Conferir o resultado do CI depois do último push (backend e APK).
2. Subir o ambiente na Azure (`AZURE.md`) e fazer as configurações manuais de
   `SECURITY_AUDIT.md` §6.
3. ~~Segundo fator para o admin; troca e recuperação de senha~~ (feito na 2ª rodada, abaixo).
4. Testar o APK num celular (Keystore, atestação, pinning) e a facial em mais aparelhos.
5. Definir as contas PJ de teste do pentest e preencher período/contato no `PENTEST.md`.

## 7.1 Segunda rodada (10/10, tarde) — Claude + Codex

Trabalho em equipe (Claude Code coordenando e cuidando do backend; Codex no frontend, nos
ataques à API e na revisão independente). Instruções dos agentes: `GPT.md` e `GEMINI.md`.

- **Segurança**: auditoria 2 completa em `relatorios/AUDITORIA-2-SEGURANCA.md` — 30 achados
  corrigidos com teste (pagamento duplicado em folha/lote/Pix/pendências, colisão de chave
  interna que aprovava pendência não executada, teto de aparelho novo contornável, Pix
  Automático sem limite, NF-e repetida, MED devolvendo em dobro…), revisão cruzada,
  fuzz de invariantes (o dinheiro nunca nasce nem some) e concorrência real no Postgres.
- **Autenticação**: troca/recuperação de senha com rosto (A-16) e TOTP do admin (A-15).
- **Telas novas**: Segurança (aparelhos/sessões/atividade), editar acesso na Equipe, Folha,
  Auditoria da empresa, Contestar e Estornar, KYC no perfil, "Esqueci minha senha".
- **Lógica bancária** (`relatorios/R1-logica-bancaria.md`): split com transição honesta
  (2026 não retém), devolução de Pix por quem recebeu, apuração do mês de verdade, "A
  receber" sem cobranças pagas, saldo bloqueado visível, rendimento não retroativo,
  conciliação de operações presas, outbox de webhooks.
- **Números**: backend 454 testes (SQLite) / 457 (Postgres, rodada anterior), app 146.
- **Ainda falta do R1**: comprovante com E2E e QR Code real (exigem SPI/DICT ou parceiro),
  IR/IOF no rendimento, Pix Agendado, KYB completo (beneficiário final), encerramento de
  conta, exportação do extrato.

## 8. Rodar localmente para testar (sem documento em mãos)

Backend (na pasta `backend/`):

```sh
DATABASE_URL=sqlite:///./astro-local.db AMBIENTE=desenvolvimento \
JWT_SECRET=<qualquer texto longo> EMBEDDING_KEY=<chave Fernet> \
BIOMETRIA_STUB=0 CNPJ_PROVEDOR=stub KYC_DOCUMENTO_OBRIGATORIO=0 DOCUMENTO_PROVEDOR=stub DEPOSITO_DEMO=1 \
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

App (na pasta `app/`):

```sh
VITE_API_URL=http://localhost:8000 VITE_DOC_OPCIONAL=1 npx vite dev --port 8081
```

Abrir **http://localhost:8081**. A facial é real; o documento pode ser pulado e o CNPJ é
aceito sem consulta. Esse atalho só existe no servidor de desenvolvimento: a produção
recusa essas configurações ao iniciar.
