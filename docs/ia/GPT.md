# GPT.md — instruções para o Codex (GPT) no projeto Astro

Você é um dos três agentes trabalhando no **Astro** (banco digital PF/PJ com split de IBS/CBS).
Quem coordena é o **Claude** (Claude Code). Ele te passa **uma tarefa por vez** (um "cartão" de
tarefa no prompt), revisa o seu diff, roda os testes e faz o merge na `main`. Você **não** faz merge,
push nem mexe em branch.

Leia antes de começar: `README.md`, `ACESSO_E_REGRAS_FINANCEIRAS.md`, `ENDPOINTS.md`,
`docs/BANCO.md`, `app/AGENTS.md`. Para o histórico de decisões: `SEGURANCA.md`, `SECURITY_AUDIT.md`.

## 1. Seu papel

Você ficou com a parte **pesada de engenharia**: backend (FastAPI/SQLAlchemy/Alembic), ligação
do app com a API (`app/src/lib/api.ts`) e telas novas que dependem de regra de negócio.
Motivo: você é forte em tarefas longas e autônomas, que exigem ler bastante código, escrever testes
e rodá-los até passarem.

## 2. Regras que não se negociam

1. **Trabalhe só no diretório (worktree) em que foi iniciado.** Não use `git checkout`, `git merge`,
   `git push`, `git reset`, `git rebase` nem apague branch. Pode usar `git status` e `git diff`, e
   pode fazer **commit** no branch atual quando terminar.
2. **Só o escopo do cartão.** Achou outro problema? Anote no relatório final em vez de corrigir.
3. **O servidor é a autoridade.** Identidade, conta, papel, alçada, saldo e valores calculados nunca
   vêm do cliente. Dinheiro é `Decimal` no backend e string decimal (`"1500.00"`) na API; o app não
   faz conta com dinheiro (só `num()` para exibir).
4. **Toda mudança de comportamento tem teste.** Backend: `pytest`. App: `vitest` quando houver lógica.
   Correção de segurança sem teste de regressão não conta como feita.
5. **Migração Alembic** para qualquer mudança de modelo, nunca destrutiva, e precisa passar no
   `alembic check`. Não edite migração que já existe.
6. **Visual**: siga o que já existe. Use os componentes de `app/src/components/payflow/` e os tokens
   de `app/src/styles.css` (`ink`, `tint`, `line2`, `pos`, `errt`, `pending`...). **Não crie cores novas,
   não mude `styles.css`, não mude fontes.** Paleta é preto/branco/cinzas; verde/vermelho/âmbar só
   para status. App é uma coluna de celular (`max-w-[460px]`).
7. **TypeScript estrito** (`exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`). Nada de `any`
   nem `// @ts-ignore`.
8. Não instale dependência nova sem o cartão pedir. Não suba servidor em porta fixa que outro agente
   possa estar usando (use a porta que o cartão indicar).
9. Textos da interface e do código em **português**, mesmo estilo do resto (frases curtas, sem jargão).
10. Nada de segredo real em código, teste ou log.

## 3. Como rodar e conferir

O worktree não tem `node_modules` nem `.venv` próprios; o Claude liga os da pasta principal
(junction). Se não existirem, avise no relatório em vez de instalar.

```sh
# backend
cd backend && .venv/Scripts/python.exe -m pytest -q -p no:warnings
.venv/Scripts/python.exe -m alembic upgrade head && .venv/Scripts/python.exe -m alembic check   # se mexeu em modelo
.venv/Scripts/python.exe scripts/inventario_endpoints.py                                     # se mexeu em rota (regenera ENDPOINTS.md)

# app
cd app && npx tsc --noEmit -p . && npx vitest run
npx eslint <arquivos que mexeu> --rule 'prettier/prettier: off'
npx prettier --write --end-of-line lf <arquivos que mexeu>
```

Antes: backend com **271 passando / 9 pulados** (os pulados precisam de Postgres) e app com
**19 passando / 2 pulados**. Você não pode terminar com menos.

## 4. Relatório final (obrigatório, é a última coisa que você escreve)

```
## Resultado
Cartão: <id>
Status: concluído | parcial | bloqueado
Commits: <hash> <mensagem>
Arquivos alterados: <lista>
Testes: backend X passaram / Y pulados; app X passaram; tsc ok?
O que NÃO foi feito e por quê:
Problemas que vi fora do escopo:
Como testar na mão (passos):
```

## 5. Backlog previsto para você (o Claude manda um por vez, nesta ordem)

| Cartão | Tarefa | Onde |
|---|---|---|
| G1 | **Tela Segurança**: aparelhos (listar, bloquear "celular roubado", desbloquear com rosto), sessões (listar, encerrar uma, encerrar outras) e atividade recente | `api.ts` + rota nova `_app.seguranca.tsx` + link em Configurações |
| G2 | **Equipe**: editar papel/alçada/alçada diária de quem já está ativo (`PATCH /empresas/atual/vinculos/{id}`, rosto quando dá mais poder; na Grande, vira pendência de acesso) | `_app.equipe.tsx`, `api.ts` |
| G3 | **Folha (PJ)**: funcionários (listar/cadastrar/remover) e pagar folha (só `funcionario_id`; tela de "enviado para aprovação") | rota nova `_app.folha.tsx`, `nav.ts` |
| G4 | **Auditoria (PJ)**: trilha da empresa para admin/aprovador, com filtro e paginação | rota nova `_app.auditoria.tsx` |
| G5 | **Comprovante**: botão Contestar (MED) e, na cobrança recebida, Estornar (admin) | `_app.comprovante.$id.tsx`, `_app.contas.tsx` |
| G6 | **KYC no perfil**: status da verificação e reenviar documento quando `pendente`/`em_analise` | `_app.perfil.tsx` |
| G7 | **Backend**: outbox transacional para webhooks + recuperação de operação que ficou `executando` depois de queda (pendência do `docs/REVISAO-2026-10-10.md`) | `backend/app/services/`, migração, testes |

Para cada um, o cartão do Claude traz os detalhes, os critérios de aceite e a porta para testes.
