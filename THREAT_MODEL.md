# Astro — modelo de ameaças

Estado em 10/10/2026. Achados e evidências em `SECURITY_AUDIT.md`; rotas em `ENDPOINTS.md`.

## 1. O que é o sistema

```
 Celular (APK Android / PWA iPhone) ou navegador
   │  HTTPS · Bearer + DPoP (chave do aparelho) · X-Dispositivo-Id · X-Conta
   ▼
 [borda: Front Door + WAF  |  nginx na VM]  ──►  API FastAPI (container sem root)
                                                   │  ORM (SQLAlchemy)          │ HTTPS de saída
                                                   ▼                            ▼
                                             Postgres (rede privada)     BrasilAPI (CNPJ),
                                                                         Google (revogação da atestação),
                                                                         webhooks do ERP do cliente
 App web estático (Static Web Apps / nginx) ── só HTML/JS/CSS com CSP
```

## 2. Ativos

| Ativo | Por que importa |
|---|---|
| Saldo e movimentação das carteiras (PF e PJ) | É o dinheiro; erro aqui é perda direta |
| Regras PJ (papel, alçada, alçada diária, assinatura conjunta) | Segregação de funções dentro da empresa |
| Credenciais: hash de senha, template facial (cifrado), chaves DPoP, tokens | Tomada de conta |
| Dados pessoais: CPF, nome, documentos (KYC), selfie, celular | LGPD; biometria é dado sensível |
| Trilha de auditoria e histórico de saldo | Prova do que aconteceu; contestação (MED) |
| Segredos do servidor (`JWT_SECRET`, `EMBEDDING_KEY`, `ADMIN_SENHA`, banco) | Comprometem todo o resto |

## 3. Atores

- **Cliente legítimo** (PF; pessoa vinculada a PJ com papel e alçada).
- **Atacante externo sem conta** — força bruta, enumeração, abuso de rotas públicas.
- **Atacante com conta própria** — o caso do pentest: tenta ler/mexer no que é de outro (IDOR), driblar alçada, forjar valores.
- **Insider PJ** — operador que tenta pagar acima do que pode, aprovar a própria operação, se dar mais poder.
- **Quem rouba o aparelho / o token** — celular perdido, token copiado de log ou proxy.
- **Admin da plataforma comprometido** — senha vazada.
- **Infraestrutura/terceiros** — BrasilAPI, CDN do MediaPipe, URL de webhook do cliente.

## 4. Fronteiras de confiança

1. **Cliente → API**: tudo que vem do cliente é não confiável (corpo, headers, ids, `X-Conta`, valores). Identidade = token + prova DPoP + sessão ativa; conta = vínculo ativo conferido no servidor.
2. **Borda → API**: só os proxies listados (`PROXIES_CONFIAVEIS`, `FRONT_DOOR_ID`) podem informar o IP do cliente.
3. **API → banco**: ORM parametrizado; dinheiro em `Decimal`/`NUMERIC(14,2)`.
4. **API → internet**: chamadas de saída para destinos do cliente (webhook) passam por validação anti-SSRF.
5. **Front estático**: público por natureza; nada de segredo no bundle.

## 5. Ameaças (STRIDE) por superfície

| # | Superfície | Ameaça | Controle | Residual |
|---|---|---|---|---|
| T1 | Login | Força bruta / credential stuffing (S) | Argon2id; senha + **rosto** (2 fatores); limites por conta+IP, por conta e por IP; resposta e tempo iguais para e-mail inexistente | Botnet > 50 IPs trava a conta 15 min (A-06) |
| T2 | Login | Travar a conta de outra pessoa (D) | Bloqueio por conta+IP; conta só com 50 falhas distribuídas | Idem |
| T3 | Biometria | Foto/vídeo/câmera virtual (S) | Prova de vida com passos sorteados pelo servidor, anti-spoof, desafio de uso único; no APK, atestação do aparelho | Ataque de apresentação bem feito; calibrar em aparelho real |
| T4 | Tokens | Token roubado reutilizado (S/E) | DPoP: tokens presos à chave do aparelho (WebCrypto não exportável / Keystore); `jti` de uso único; sessão com 12 h máx. e 30 min parada; logout derruba a família | XSS no app vira "oráculo de assinatura" enquanto a página estiver aberta → CSP |
| T5 | Objetos | IDOR/BOLA: ler/apagar recurso alheio trocando id ou `X-Conta` (I/T) | Toda consulta filtra pela conta/pessoa do token; 404 sem revelar existência | — (teste cobre 19 rotas) |
| T6 | PJ | Operador paga acima do que pode; fraciona; usa lote (E/T) | Alçada por operação **e diária**, conferida também dentro do lock; acima → pendência | — |
| T7 | PJ | Aprovar a própria operação; aprovar duas vezes; corrida entre aprovadores (E) | Autor nunca aprova; cada pessoa uma vez; contagem com `FOR UPDATE` | — |
| T8 | PJ | Admin da Grande paga valor alto sozinho (E) | Assinatura conjunta acima de `LIMITE_DUAS_APROVACOES_REAIS` para todos | Empresas PME/MEI: admin sem limite por desenho |
| T9 | PJ | Pendência velha ou de alguém já desligado é aprovada (T) | Validade 72 h; autor sem vínculo ativo → cancelada | — |
| T10 | PJ | Dar-se mais poder; convite capturado (E) | Só admin gere acesso; dar poder exige rosto; Grande: quatro olhos; convite só para o dono do CPF com KYC + rosto | Dois admins em conluio |
| T11 | Dinheiro | Valor negativo/decimal estranho, saldo negativo, gasto duplo em paralelo (T) | `Decimal(gt=0, 2 casas)`; saldo checado e debitado na mesma transação com lock | Concorrência provada só no CI com Postgres |
| T12 | Dinheiro | Repetição/replay duplicando Pix (T) | `Idempotency-Key` única no banco, por conta; outra operação com a mesma chave → 409; DPoP `jti` único | — |
| T13 | Dinheiro | Golpe: dinheiro sai e some (R) | Bloqueio cautelar em destino novo ≥ R$ 1.000; MED/contestação; limites noturno e de aparelho novo | Engenharia social fora do sistema |
| T14 | Webhook | SSRF para rede interna/metadados (I/E) | https, portas 443/8443, sem IP interno, DNS conferido na entrega, sem redirect, erro genérico | DNS rebinding → egress na infra |
| T15 | Upload | Arquivo malicioso para quem analisa o KYC (E) | Tipo pelos bytes, teto de tamanho, PDF com JS/anexo recusado | Visualizador do analista |
| T16 | API | Payload gigante / consulta enorme (D) | Teto de corpo (também chunked); listas com `le=200`; limite de concorrência da biometria | Volume distribuído → WAF |
| T17 | API | Erro com detalhe interno (I) | problem+json genérico com `request_id`; validação não ecoa valor; Swagger desligado em produção | — |
| T18 | Front | XSS (T/E) | React escapa; CSP com hash dos scripts inline, sem `unsafe-inline` em script; sem source maps | CSP dentro do APK ainda não aplicada |
| T19 | Admin | Senha do admin vazada (E) | Admin desligado em produção sem lista de IPs; com a lista, senha + TOTP de uso único (A-15); ações na trilha | Segredo TOTP único do ambiente |
| T20 | Segredos | Segredo no código/imagem/log (I) | Só ambiente; produção não sobe sem segredos fortes; imagem sem `.env`; logs sem token/senha | Usuário do banco com DDL (A — §6 da auditoria) |
| T21 | Logs | Apagar rastros; forjar linha de log (R) | Trilha no banco + evento no log JSON (escapa quebra de linha); falha da trilha não perde o Pix | Trilha na mesma base da API → exportar |
| T22 | Supply chain | Biblioteca vulnerável/modelo trocado (T) | `pip-audit`/`npm audit`; versões fixadas; modelos da biometria com SHA-256 fixado; raízes da atestação fixadas | Dependências de build (`uuid`) |

## 6. Riscos residuais aceitos (resumo)

Segredo TOTP único para o admin de operação; recuperação de senha que recusa mais rápido quando ninguém confere (A-16); WAF
Standard sem regras gerenciadas e origem alcançável sem WAF; DNS rebinding em webhook;
concorrência e migração no Postgres provadas só no CI; trilha de auditoria na mesma base;
recursos do APK sem teste em aparelho. Detalhe e ordem de correção: `SECURITY_AUDIT.md` §5 e §7.
