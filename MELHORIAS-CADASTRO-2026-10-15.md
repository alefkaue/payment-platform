# Melhorias no cadastro e na verificação facial — 15/10/2026

Branch: `melhorias/cadastro-facial-2026-10-15` (a partir da `main` em `dd84e97`).
A aplicação no Azure foi **pausada** antes destas mudanças (API e front desativados,
PostgreSQL parado, dados preservados). Estas mudanças **ainda não foram publicadas no Azure**.

## O que foi feito

### 1. Data de nascimento: nada no futuro e menor de idade barrado na hora
- App (`app/src/lib/nascimento.ts`, `app/src/routes/criar-conta.tsx`):
  - o campo de data tem `max` = data de hoje, então o calendário não oferece datas futuras;
  - assim que a data é preenchida, aparece o aviso embaixo do campo: data no futuro ou
    pessoa com menos de 18 anos. O botão "Continuar" também barra, antes do documento e
    da câmera.
- Servidor (`backend/app/services/contas_service.py`): recusa data no futuro com
  mensagem própria. A regra de 18 a 120 anos já existia e roda **antes** da biometria.
- Testes: `app/src/lib/nascimento.test.ts`; `test_cadastro_recusa_nascimento_futuro_ou_menor`
  em `backend/tests/test_pentest_20261010.py`.

### 2. Rosto do documento não é mais comparado com a selfie (o documento continua)
- `backend/app/services/documento_service.py`: retirada a comparação do rosto do RG/CNH/CIN/
  passaporte com a selfie da prova de vida. O documento continua **obrigatório**: frente e
  verso, validação do arquivo, e conferência de CPF, nome, nascimento, validade, MRZ e QR.
  O resultado agora registra `verificacoes.rosto = "nao_comparado"`.
- O texto da etapa "Documento com foto" no app não fala mais em conferir o rosto.
- O teste antigo que exigia reprovar por "rosto divergente" foi trocado por um que garante
  que o rosto não muda a decisão e que a produção continua sem aprovação automática.
- A biometria continua na prova de vida (cadastro e login).

### 3. Piscar de olhos mais confiável
**Causa encontrada.** O app e o servidor usavam limiares **fixos** no sinal `eyeBlink` do
MediaPipe: o app contava olho fechado acima de 0,5 e aberto abaixo de 0,2; o servidor,
0,45 e 0,30. Quem tem olhos mais fechados, usa óculos ou olha para baixo para o celular
fica com o olho **aberto** já em 0,25 a 0,35. Assim a piscada nunca "reabria", o passo não
andava e o servidor contava 0. Além disso, girar a cabeça infla o `eyeBlink` e gerava
piscadas falsas, que podiam cair em "Pisque só quantas vezes foi pedido".

**Correção.**
- Calibração por pessoa: a base é o olho aberto da própria pessoa (percentil 20 dos
  últimos quadros), e os limiares passam a ser relativos a ela.
  - Servidor (`liveness_logic.limiares_piscada`): fechado = base + 0,25 (entre 0,35 e
    0,75); aberto = base + 0,12 (no mínimo 0,30). Nunca fica mais rígido que antes.
  - App (`app/src/lib/piscadas.ts`): limiares um pouco **mais exigentes** que os do
    servidor. Se o app deu o passo por feito, o servidor também aceita.
- A calibração começa já no preparo da câmera, antes do primeiro passo.
- Quadros com o rosto virado (|yaw| > 0,18) não contam piscada, nem no app nem no servidor.
- A gravação rápida de quadros enquanto o olho fecha usa o mesmo limiar calibrado. Antes
  era fixo em 0,4 e podia não gravar o olho fechado de quem tem a base alta.
- Testes: `backend/tests/test_piscar_calibrado.py` e `app/src/lib/piscadas.test.ts`. O
  caso "olho aberto em 0,34" contava **0** piscadas antes e agora conta 3.

## Verificação
- Backend: suíte completa sem falhas (mais 7 testes novos de piscar e nascimento). `test_instalacao_containers.py` fica fora porque
  falha só no Windows, por conferir permissão de arquivo Unix; já falhava antes.
- App: 282 testes passando, `tsc` sem erros, build de produção ok.
- **Não testado com pessoas reais.** Os testes usam séries sintéticas de `eyeBlink`.

## O que ainda falta
1. **Teste real do piscar** com a equipe: celulares diferentes, com e sem óculos, luz
   fraca, olhando para baixo. Em `npm run dev` o overlay mostra `olho fechado` e a contagem
   ao vivo.
2. **Calibrar `PISCADAS_EXTRAS`** (servidor, hoje 1). No cadastro, que leva cerca de 20 s,
   piscadas naturais durante "sorrir/virar" ainda contam para o limite de "piscar demais".
   Ignorar quadros virados reduz o problema, mas não o elimina. Se ainda houver recusas,
   medir antes de afrouxar, porque esse limite protege contra o "vídeo universal".
3. **Publicar no Azure.** Juntar esta branch na `main` e rodar o workflow "Azure Students -
   imagens de teste" (api_url = URL da API). Depois trocar as imagens com
   `az containerapp update`, religar o PostgreSQL e estender a tag `testUntilUtc`
   (ação "retomar"). Não há migração de banco nesta mudança.
4. Perfil (`_app.perfil.tsx`): as mensagens antigas sobre "rosto do documento" continuam
   só para documentos analisados antes desta mudança. Podem sair depois.
5. Formatação (prettier) já pendente na `main`, em `liveness.tsx` linha ~593. Não vem
   desta mudança.
