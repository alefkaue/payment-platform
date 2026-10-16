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

## Atualização (15/10, noite): o documento precisa ser um documento

Antes, na coleta acadêmica (`DOCUMENTO_VERIFICAR_IDENTIDADE=0`, o modo do Azure), qualquer
imagem válida passava, inclusive uma foto sem conteúdo. Agora `backend/app/services/documento_forma.py`
confere se a imagem **é um documento de identidade**, sem conferir **quem** é a pessoa:

- Cada foto (frente e verso) precisa ter conteúdo. Foto lisa, preta, branca ou só
  desfoque é recusada pela variação de tons e pela densidade de bordas.
- O conjunto precisa ter sinais de documento:
  - termos impressos lidos pelo OCR (Tesseract, já presente na imagem de produção). Os
    fortes, como "REPÚBLICA FEDERATIVA", "CARTEIRA DE IDENTIDADE", "REGISTRO GERAL",
    "HABILITAÇÃO", "DETRAN", "FILIAÇÃO" e "PASSAPORTE", valem 2 pontos. Os fracos, como
    "NOME", "VALIDADE", "CPF" e formato de CPF/data, valem 1;
  - passa com 3 pontos, ou com 2 pontos e uma foto 3x4 detectada no documento;
  - QR code ou MRZ bastam sozinhos;
  - sem OCR, exige a foto 3x4.
- A foto 3x4 é só **detectada**: nada é comparado com a selfie. CPF e nome também não são
  conferidos na coleta acadêmica.
- A recusa é um HTTP 400 com orientação ("Envie a frente e o verso do RG, CNH, CIN ou
  passaporte, inteiros, nítidos e sem reflexo"). O app volta para a etapa do documento.
- Testes: `backend/tests/test_documento_forma.py`, com 12 casos: foto vazia, verso vazio,
  imagem qualquer, selfie, RG com texto, OCR parcial com 3x4, QR, sem OCR e OCR com falha.

**Falta:** calibrar com fotos reais de RG/CNH tiradas pelo celular. Os testes simulam o
OCR, porque o Tesseract não está instalado neste PC. Se documentos verdadeiros forem
recusados, baixar `PONTOS_SO_TEXTO` ou acrescentar termos em `TERMOS_FORTES`. O log
`Documento recusado por não parecer identidade` mostra os pontos e os termos lidos.

**Publicado no Azure em 15/10 às 21:51:** API e front com o commit `7908dcb`
(`/saude`, `/pronto` e `/criar-conta` respondem 200).

## Pedido para a próxima sessão (recebido às 21:50 e não feito até as 22:00)

### A. Erro "Identidade do titular ainda não aprovada para movimentação" (fazer instantâneo)
- **Origem:** `backend/app/repositories/repository.py`, `_exigir_identidade_financeira`.
  Em produção (o Azure usa `AMBIENTE=producao`), qualquer movimentação exige
  `kyc_status == "aprovado"`. A coleta acadêmica sempre grava o documento como
  `em_analise`, então ninguém consegue movimentar.
- **Ideia de correção (não aplicada):** no modo de demonstração acadêmica
  (`DEMONSTRACAO_PUBLICA=1`, já ligado no Azure por `demonstracaoPublica`), aceitar
  também `em_analise` ou pular a checagem. Registrar no relatório como desvio proposital.
- **Por que não foi feito:** o Claude Code bloqueou a alteração por remover um controle
  de segurança. Precisa de autorização explícita da equipe (regra de permissão) ou de
  ser feita por uma pessoa.
- Pontos relacionados que também exigem `aprovado` ou `em_analise`:
  `contas_service.py:118` e `equipe_service.py:279`.

### B. Biometria no pagamento só acima de um valor, como Inter e outros bancos
- Pedido: em aparelho reconhecido e autorizado, pagamento sem biometria. Pedir o rosto só
  acima de um valor: padrão **R$ 1.000**, alterável nas configurações do usuário.
- O que já existe: `LIMITE_FACIAL_REAIS` (padrão R$ 500, `backend/app/core/config.py:110`)
  e `_limite_facial()` em `pagamento_service.py`, usado nas linhas 223, 266, 427, 514 e 585.
  Também há a regra de **aparelho novo** do Banco Central (`DISPOSITIVO_NOVO_*`).
- A fazer:
  1. pesquisar e documentar como Inter, Nubank e Itaú tratam aparelho confiável e valor
     mínimo para biometria;
  2. mudar o padrão para 1.000;
  3. criar um limite **por usuário**, editável em Configurações/Perfil, com teto no
     servidor e mudança que exige rosto e só vale após carência, como os limites atuais;
  4. aparelho reconhecido = aparelho já vinculado e fora da carência de aparelho novo;
  5. testes de pagamento abaixo e acima do limite, em aparelho novo e em aparelho
     reconhecido.
