# ASTRO — Checklist de melhorias de lógica, segurança e frontend

## Objetivo deste documento

Este documento consolida o que precisa ser corrigido ou melhorado no projeto **Astro**, com base em:

- análise do repositório `alefkaue/payment-platform`;
- análise do `README.md`, `HANDOFF.md` e `PLANO.md`;
- inspeção de partes do frontend e dos fluxos de login, cadastro, equipe e aprovações;
- comparação com fluxos publicados por bancos brasileiros para contas PJ;
- referência às regras de segurança do Banco Central para Pix.

> **Objetivo da entrega:** o Astro será apresentado para uma banca com foco principal no frontend, mas o frontend precisa representar uma lógica de banco plausível. Não é necessário transformar o projeto em um banco real; é necessário eliminar comportamentos que contradigam o modelo apresentado.

---

# 1. Diagnóstico geral

O projeto já evoluiu bastante na parte de arquitetura.

Atualmente o backend já possui conceitos importantes:

- pessoa separada de empresa;
- vínculo pessoa ↔ empresa;
- papéis `admin`, `aprovador`, `operador` e `consulta`;
- alçada financeira;
- dupla aprovação;
- aparelho;
- limites;
- biometria com prova de vida;
- bloqueio cautelar;
- contestação;
- chaves Pix;
- validação de CNPJ;
- idempotência;
- dinheiro como `Decimal/string`;
- API FastAPI;
- frontend separado;
- modo de demonstração e modo API.

O problema principal agora não é "falta de funcionalidade". É **coerência entre o que o sistema diz ser e o que a interface realmente permite fazer**.

Os pontos prioritários são:

1. corrigir o onboarding PJ;
2. remover o certificado digital como autenticação principal do usuário PJ;
3. transformar o modelo de usuários PJ em um fluxo completo e coerente;
4. fazer o frontend refletir permissões reais;
5. reforçar autenticação e segurança de operações;
6. corrigir o fluxo de dispositivo novo;
7. transformar a tela de equipe em um verdadeiro gerenciamento de acesso;
8. melhorar o fluxo de aprovação;
9. corrigir inconsistências entre modo demonstração e backend;
10. corrigir o layout da apresentação em tela reduzida e criar o modo expandido do celular;
11. deixar claro na documentação o que é simulado e o que é funcional.

---

# 2. Modelo correto de identidade

## 2.1 Regra principal

A regra que deve orientar o projeto inteiro é:

> **O login pertence à pessoa. A conta pertence à pessoa ou à empresa.**

Para PF:

```text
Pessoa
  ↓
CPF
  ↓
Conta PF
```

Para PJ:

```text
Pessoa
  ↓
CPF + credencial
  ↓
Vínculo com empresa
  ↓
CNPJ
  ↓
Conta PJ
```

A pessoa não deve "logar como CNPJ".

Ela se autentica como pessoa e, depois, o sistema determina quais empresas ela pode operar.

O projeto já implementa essa ideia no backend e no seletor de conta, portanto o frontend de login deve seguir essa mesma lógica sem apresentar o certificado e-CNPJ como login cotidiano.

---

# 3. Cadastro PF

## Estado atual

O cadastro PF já possui:

- nome;
- e-mail;
- senha;
- CPF;
- prova de vida facial.

Isso é uma boa base.

## Melhorias

### 3.1 Separar identificação de autenticação

O cadastro deve ficar conceitualmente assim:

```text
CPF
Nome
Data de nascimento
E-mail
Celular
Senha/credencial
Documento de identidade
Verificação de identidade
Prova de vida
```

Não é necessário implementar todos os documentos reais para a apresentação, mas a interface deve deixar claro que existe um processo de KYC.

### 3.2 Documento

Adicionar, se houver espaço no fluxo:

- tipo de documento;
- RG/CNH;
- número;
- órgão emissor;
- UF;
- validade quando aplicável.

Para a demo, o upload pode ser simulado.

### 3.3 Celular

Adicionar confirmação do celular por código.

O próprio projeto já reconhece que e-mail/celular ainda não possuem confirmação por código.

Implementar:

```text
Celular
 ↓
Enviar código
 ↓
Usuário informa código
 ↓
Celular confirmado
```

O código pode ser simulado no modo demonstração.

---

# 4. Cadastro PJ — maior correção necessária

## Problema atual

O `criar-conta.tsx` ainda apresenta:

- CNPJ;
- representante;
- CPF do representante;
- facial;
- certificado e-CNPJ para determinadas empresas.

O problema é principalmente conceitual:

> **O e-CNPJ não deve ser apresentado como a credencial diária do funcionário ou como a autenticação normal da conta PJ.**

Bancos empresariais reais possuem usuários individuais e perfis de acesso. O Santander, por exemplo, diferencia Usuário Master e Usuários Secundários, com responsabilidades e acessos definidos pelo Master. Também possui perfis de acesso e autorização. 

## Modelo recomendado

### Etapa 1 — Dados da empresa

```text
CNPJ
Razão social
Nome fantasia
Porte
Setor
Endereço
Regime tributário
```

### Etapa 2 — Representante legal

```text
Nome
CPF
Documento
Celular
E-mail
```

### Etapa 3 — Validação da empresa

```text
CNPJ
 ↓
Validação do CNPJ
 ↓
Situação cadastral
 ↓
Representante
 ↓
Quadro societário / representação
```

O backend já valida CNPJ e pode verificar o CPF do responsável no quadro societário quando a fonte fornece essa informação.

### Etapa 4 — Documentação

Para uma implementação mais realista, o fluxo pode apresentar:

- cartão CNPJ;
- contrato social;
- CCMEI para MEI;
- documento do representante;
- comprovante de endereço;
- informações dos beneficiários finais, quando aplicável.

Para a apresentação, os documentos podem ser apenas simulados.

### Etapa 5 — Prova de identidade

O representante realiza:

```text
Prova de vida
+
Reconhecimento facial
```

A finalidade aqui é provar a identidade da pessoa que está abrindo a conta.

### Etapa 6 — Análise

```text
Dados enviados
 ↓
KYC/KYB
 ↓
Conta aprovada
```

Não precisa simular uma análise burocrática completa.

---

# 5. O certificado digital

## O que NÃO fazer

Não apresentar:

> "PME e grande empresa precisam entrar no banco usando e-CNPJ."

Isso cria uma lógica errada para o uso cotidiano.

## O que fazer

O certificado pode aparecer como:

> **Recurso corporativo opcional / integração empresarial**

Por exemplo:

- assinatura de determinados documentos;
- integração com sistemas empresariais;
- operações que realmente dependam de certificado;
- integração fiscal.

Mas o usuário cotidiano continua sendo uma pessoa.

### Regra:

```text
e-CNPJ
≠
login diário de todos os funcionários
```

---

# 6. Usuários PJ

Esta é uma das partes mais importantes do projeto.

Bancos empresariais reais possuem gerenciamento de usuários. O Santander documenta explicitamente Usuário Master, Usuário Secundário, perfis de acesso e perfis de autorização. O Master cria os usuários secundários e define os acessos.

O Astro já possui backend para isso. O frontend precisa terminar de representar esse modelo.

## Modelo

```text
Empresa
   ↓
Conta PJ
   ↓
Vínculos
   ↓
Pessoas
```

Exemplo:

```text
João
CPF XXX
Papel: Administrador

Maria
CPF XXX
Papel: Operador
Alçada: R$ 50.000

Carlos
CPF XXX
Papel: Consulta

Ana
CPF XXX
Papel: Aprovador
```

---

# 7. RH x administrador bancário

Não misturar os conceitos.

O RH pode existir como parte do fluxo corporativo, mas o banco precisa de uma autoridade própria para conceder acesso à conta.

O modelo recomendado é:

```text
RH
 ↓
Funcionário existe na empresa

Administrador da conta
 ↓
Concede acesso bancário

Banco
 ↓
Cria vínculo e aplica permissões

Funcionário
 ↓
Ativa sua própria credencial
```

Não é necessário implementar um sistema completo de RH.

Para o projeto:

> **O administrador da conta PJ cadastra o usuário bancário.**

Opcionalmente, pode existir uma indicação:

> "Funcionário verificado pela empresa."

---

# 8. Tela "Equipe"

## Estado atual

A tela `/equipe` já possui:

- adicionar pessoa;
- nome;
- e-mail;
- papel;
- alçada;
- lista de usuários.

Isso é bom, mas ainda é simples demais.

## Alterar para

### Lista

```text
EQUIPE

João Silva
Administrador
Acesso completo

Maria Souza
Financeiro
Até R$ 50.000

Carlos Lima
Contabilidade
Somente consulta
```

### Ao clicar em uma pessoa

Abrir:

```text
Dados
Status
Papel
Permissões
Alçada
Dispositivo
Último acesso
Data de criação
```

### Ações

- Alterar permissões;
- Alterar alçada;
- Suspender acesso;
- Revogar acesso;
- Reativar;
- Ver atividade.

---

# 9. CPF deve existir no cadastro do usuário PJ

Atualmente a tela de equipe usa principalmente:

- nome;
- e-mail;
- papel;
- alçada.

Para um modelo bancário mais consistente, o usuário deve estar vinculado a uma pessoa identificável.

Adicionar:

```text
Nome
CPF
E-mail
Celular
Cargo/função
Papel bancário
```

O CPF não precisa ser exibido inteiro na lista.

Exemplo:

```text
***.***.123-**
```

---

# 10. Convite/ativação do usuário

O sistema não deve criar uma senha para o funcionário.

Fluxo recomendado:

```text
Administrador adiciona pessoa
       ↓
CPF + dados
       ↓
Banco verifica se pessoa existe/cadastro
       ↓
Acesso fica "Pendente de ativação"
       ↓
Funcionário acessa o aplicativo oficial
       ↓
Informa CPF/e-mail
       ↓
Realiza ativação
       ↓
Cria sua própria credencial
       ↓
Registra dispositivo
       ↓
Conta ativa
```

Um SMS/e-mail pode servir apenas como aviso ou etapa de ativação.

Não tratar um link enviado por SMS como prova suficiente de identidade.

---

# 11. Autenticação

## Problema atual

O login ainda possui:

```text
Conta
Senha
```

e apresenta:

```text
Entrar com biometria
```

Além disso, o comportamento de PJ ainda apresenta:

```text
Entrar com certificado digital
```

Isso deve ser removido como login principal.

## Modelo recomendado

### Login básico

```text
CPF/e-mail
+
senha ou passkey
```

### Autenticação forte

Adicionar MFA.

Preferência para:

```text
Passkey/WebAuthn
```

ou:

```text
Senha
+
segundo fator
```

A biometria pode ser utilizada localmente pelo dispositivo para liberar a credencial, ou como prova de identidade/step-up.

Não tratar "facial" como única tecnologia de segurança.

---

# 12. Biometria facial

A prova de vida implementada é uma boa funcionalidade para demonstração.

O projeto já possui:

- desafio;
- movimento da cabeça;
- anti-spoofing;
- comparação facial;
- validade do desafio;
- processamento no servidor.

Manter.

## Melhorar o texto da interface

Evitar:

> "Reconhecimento facial do titular."

Preferir:

> "Verificação de identidade por reconhecimento facial."

Para PJ:

> "O representante realiza a verificação de identidade na abertura. Os demais usuários possuem credenciais individuais."

Isso evita a ideia errada de que o rosto do dono controla todos os funcionários.

---

# 13. Dispositivo confiável

Essa é uma das partes mais interessantes do backend.

O Banco Central possui mecanismos de cadastro de dispositivo para Pix e impõe limites para transações iniciadas em dispositivos não cadastrados. 

O Astro já possui:

```text
X-Dispositivo-Id
```

e lógica de dispositivo confiável.

## Melhorar a interface

Criar:

### Segurança → Dispositivos

```text
MEUS DISPOSITIVOS

Este celular
Confiável
Último acesso: agora

Notebook da empresa
Confiável
Último acesso: ontem

Celular antigo
Bloqueado
```

Ações:

> Remover dispositivo

> Bloquear dispositivo

Isso deixa o modelo muito mais compreensível para a banca.

---

# 14. Celular roubado

O sistema precisa demonstrar o que acontece.

Fluxo:

```text
Usuário perde celular
 ↓
Entra por outro dispositivo
 ↓
Segurança
 ↓
Dispositivos
 ↓
Bloquear celular perdido
 ↓
Credencial daquele dispositivo deixa de ser confiável
```

Não basta trocar senha.

---

# 15. Autorização financeira

A autenticação responde:

> "Quem é você?"

A autorização responde:

> "O que você pode fazer?"

O Astro deve deixar isso muito claro.

Exemplo:

```text
Maria
Papel: Operadora
Alçada: R$ 50.000

Pagamento R$ 20.000
→ executa

Pagamento R$ 80.000
→ fica pendente

João
Papel: Aprovador
→ aprova
```

O backend já possui esse conceito.

---

# 16. Perfil de acesso x perfil de autorização

Separar os dois conceitos no frontend.

## Perfil de acesso

Define o que a pessoa pode visualizar/fazer:

```text
✓ Saldo
✓ Extrato
✓ Pix
✓ Pagamentos
✓ Cobranças
✗ Equipe
✗ Configurações administrativas
```

## Perfil de autorização

Define o poder de aprovar:

```text
Pode aprovar?
Sim

Alçada:
R$ 500.000

Quantidade de aprovadores:
1
```

O Santander utiliza exatamente essa distinção em seu Internet Banking Empresarial.

---

# 17. Aprovação dupla

A tela `/pendentes` já existe.

Manter o conceito de maker-checker.

Fluxo:

```text
Operador
 ↓
Cria pagamento
 ↓
Valor ultrapassa alçada
 ↓
Pendente
 ↓
Aprovador recebe notificação
 ↓
Visualiza detalhes
 ↓
Autentica novamente, se necessário
 ↓
Aprova / recusa
 ↓
Pagamento executado
```

## Melhorar a tela

Mostrar:

- quem criou;
- quando criou;
- beneficiário;
- banco;
- valor;
- motivo;
- alçada do criador;
- risco;
- quantas aprovações faltam;
- quem aprovou;
- status.

---

# 18. Não usar somente valor como regra de segurança

Atualmente a lógica de alçada é boa, mas o sistema pode demonstrar um motor de risco simples.

Exemplo:

```text
Pagamento:
R$ 2.000
Beneficiário conhecido
Dispositivo confiável
Horário normal
→ baixo risco
```

Outro:

```text
Pagamento:
R$ 300.000
Beneficiário novo
Dispositivo novo
Horário incomum
→ alto risco
```

Resultado:

```text
Autenticação adicional
+
Aprovação
+
Possível retenção/análise
```

O Banco Central prevê mecanismos de análise e tratamento diferenciado para transações suspeitas.

---

# 19. Horários

A ideia de horário é válida, mas não deve ser a única regra.

Em vez de:

> "Só pode pagar funcionário das 9h às 18h."

Usar políticas:

```text
Tipo de operação
Valor
Horário
Beneficiário
Dispositivo
Localização
Histórico
```

O servidor calcula um risco.

Para a banca, pode ser mostrado como:

> **Transação normal**

ou

> **Transação requer autenticação adicional**

---

# 20. Pix

O Pix está bem encaminhado conceitualmente.

Manter:

- enviar;
- receber;
- chave;
- QR;
- copia e cola;
- consulta;
- limites.

## Corrigir/explicar claramente

Pix comum:

```text
Pix
→ transferência
→ SEM split tributário
```

Cobrança com nota:

```text
Venda
→ cobrança
→ nota fiscal
→ split
```

Isso já está corrigido no backend e deve continuar igual no frontend.

---

# 21. Split

O maior cuidado é não transformar o split em uma "taxa do banco".

O sistema deve comunicar:

```text
Valor da venda
        ↓
Nota fiscal
        ↓
Valor tributário destacado
        ↓
Split
        ↓
Valor líquido + tributo separado
```

Transferência normal não deve disparar split.

O `HANDOFF.md` já corrigiu esse conceito no backend.

---

# 22. Cobrança

A tela de cobrança precisa deixar mais claro:

```text
Criar cobrança
 ↓
Valor
 ↓
Cliente
 ↓
Nota fiscal
 ↓
Parcelamento
 ↓
Pix / boleto
 ↓
Cobrança emitida
 ↓
Pagamento
 ↓
Split
```

No momento, Pix copia e cola e boleto são simulados. Isso deve ser indicado na documentação e, se possível, discretamente na interface de apresentação.

---

# 23. Estorno

O backend possui estorno, mas o frontend ainda não apresenta o fluxo completo.

Adicionar:

```text
Comprovante
 ↓
Estornar
 ↓
Confirmar
 ↓
Motivo
 ↓
Autenticação
 ↓
Estorno
```

Para cobrança com split, mostrar a devolução do valor e o tratamento do valor tributário conforme o estado do repasse.

---

# 24. Contestação / MED

O backend já possui endpoint de contestação, mas falta o botão no comprovante.

Adicionar:

```text
Comprovante
 ↓
Mais opções
 ↓
Contestar transação
 ↓
Motivo
 ↓
Confirmar
 ↓
Protocolo
```

Depois:

```text
Status:
Em análise
```

---

# 25. Notificações

A central de notificações já existe.

Adicionar notificações de segurança:

```text
Novo dispositivo cadastrado
Pagamento criado
Pagamento aprovado
Pagamento recusado
Novo usuário adicionado
Permissão alterada
Limite alterado
Dispositivo bloqueado
```

Para PJ, isso é especialmente importante.

---

# 26. Auditoria

Adicionar uma área:

> **Segurança → Atividade da empresa**

Exemplo:

```text
Hoje, 14:32
Maria criou um pagamento de R$ 80.000

Hoje, 14:36
João aprovou o pagamento

Hoje, 14:37
Pagamento enviado
```

Também:

```text
13:10
Novo usuário adicionado

13:11
Perfil "Operador" atribuído

13:12
Alçada definida em R$ 50.000
```

Isso é extremamente útil para uma apresentação de Cibersegurança.

---

# 27. Frontend — arquitetura visual

O app já foi transformado para uma moldura de celular de até 460px.

Isso é adequado para a apresentação.

O problema é que uma interface de celular dentro de um slide/iframe pode sofrer com redução de viewport.

## Requisito

Criar dois estados:

### Normal

```text
slide
 └── celular
```

### Expandido

Ao clicar duas vezes no celular:

```text
████████████████████████
█                      █
█       CELULAR        █
█                      █
████████████████████████

fundo escuro/opaco
```

O celular deve:

- ficar centralizado;
- aumentar de tamanho;
- manter proporção;
- ficar acima do restante da apresentação;
- receber `z-index` alto;
- bloquear o scroll do fundo;
- permitir fechar com segundo clique, ESC ou botão;
- funcionar dentro da apresentação HTML.

---

# 28. Modal de celular expandido

Implementar um componente global, por exemplo:

```text
PhonePresentationFrame
```

Estados:

```text
isExpanded = false
```

Ao duplo clique:

```text
isExpanded = true
```

Aplicar:

```text
position: fixed
inset: 0
background: rgba(...)
backdrop-filter: ...
display: flex
align-items: center
justify-content: center
z-index: máximo
```

No celular:

```text
max-width
max-height
width
aspect-ratio
```

Não simplesmente aumentar `scale()` sem considerar viewport.

---

# 29. Problema de layout em tela reduzida

Testar principalmente:

- 390 × 844;
- 375 × 812;
- 360 × 800;
- 430 × 932;
- iframe menor que 390px;
- desktop com moldura de celular.

Não confiar apenas no desktop.

O próprio `HANDOFF.md` alerta que os breakpoints CSS podem enxergar a viewport real em vez da largura interna esperada da moldura.

---

# 30. Navegação

A navegação inferior de 5 itens é adequada para mobile.

Manter:

```text
Início
Pix
Extrato
Cartões
Mais
```

Mas garantir que PF e PJ tenham menus adequados.

### PF

```text
Início
Pix
Extrato
Cartões
Mais
```

### PJ

```text
Início
Pix
Extrato
Equipe
Mais
```

Dentro de "Mais":

```text
Cobranças
Aprovações
Split
Notificações
Perfil
Segurança
Configurações
Sair
```

Não mostrar funcionalidades que o usuário não pode executar.

---

# 31. Controle de acesso no frontend

Não basta esconder botões por aparência.

O backend deve continuar sendo a autoridade.

Frontend:

```text
se papel == consulta
→ não mostra botão de pagamento
```

Backend:

```text
POST /pagamento
→ verifica papel novamente
→ verifica alçada
→ verifica conta
→ verifica dispositivo
→ verifica limites
```

Nunca confiar somente no frontend.

---

# 32. Conta selecionada

O seletor atual PF ↔ PJ é uma boa solução.

Melhorar visualmente para deixar explícito:

```text
Você está operando:

ASTRO INDÚSTRIA LTDA
CNPJ: **.***.***/****-**
```

Evitar qualquer dúvida sobre qual conta está sendo movimentada.

Antes de um pagamento:

```text
Origem
ASTRO INDÚSTRIA LTDA
Conta ****1234
```

Isso reduz risco de erro operacional.

---

# 33. Pagamento

Antes de confirmar:

```text
Pagar

De:
Astro Indústria Ltda

Para:
Fornecedor ABC Ltda

CNPJ:
**.***.***/****-**

Valor:
R$ 80.000,00

Data:
09/10/2026

Autorização:
Requer 2º aprovador
```

Depois:

> Confirmar pagamento

---

# 34. Comprovante

O comprovante precisa ser mais completo.

Mostrar:

- valor;
- data;
- hora;
- pagador;
- recebedor;
- documento mascarado;
- instituição;
- identificador;
- status;
- autor da operação;
- aprovador;
- eventual retenção/bloqueio.

---

# 35. Configurações

A tela `/config` deve ser dividida em:

## Conta

- dados;
- agência;
- conta;
- chaves Pix.

## Segurança

- autenticação;
- dispositivos;
- biometria;
- sessões;
- recuperação.

## PJ

- usuários;
- papéis;
- alçadas;
- aprovações;
- atividade.

## Cartão

- cartão virtual;
- limite;
- bloqueio;
- compras online;
- internacional.

---

# 36. Sessões

Adicionar:

```text
Sessões ativas

Este celular
Agora

Chrome — Windows
Hoje 20:31

Notebook da empresa
Ontem 14:20
```

Ações:

> Encerrar sessão

> Encerrar todas

Isso é uma melhoria importante de segurança.

---

# 37. Recuperação de conta

Não permitir que "esqueci a senha" seja um caminho fraco.

Fluxo conceitual:

```text
Esqueci minha senha
 ↓
CPF/e-mail
 ↓
Segundo fator
 ↓
Verificação de identidade
 ↓
Nova credencial
```

Para PJ, ações de recuperação devem respeitar o vínculo da pessoa com a empresa.

---

# 38. Tokens

O `HANDOFF.md` informa que tokens estão em `sessionStorage` e considera isso aceitável para web, mas indica migrar para armazenamento seguro no APK.

Para o projeto:

### Web

Pode continuar temporariamente.

### Android

Migrar para:

> Capacitor Preferences / armazenamento seguro adequado, preferencialmente com mecanismo protegido do sistema.

Não guardar tokens sensíveis em armazenamento simples se o app for tratado como produto final.

---

# 39. Backend — pontos prioritários

## Alta prioridade

### 39.1 Gestão completa de vínculos

Já existe no backend.

Falta:

- editar;
- suspender;
- remover;
- reativar;
- consultar histórico;
- registrar quem fez a alteração.

### 39.2 Auditoria

Criar eventos para:

```text
USER_CREATED
USER_SUSPENDED
USER_REVOKED
ROLE_CHANGED
LIMIT_CHANGED
DEVICE_ADDED
DEVICE_REVOKED
PAYMENT_CREATED
PAYMENT_APPROVED
PAYMENT_REJECTED
```

### 39.3 Segurança de aprovação

O aprovador deve autenticar a decisão, principalmente em operações de alto risco.

### 39.4 Verificação de sessão

Verificar:

- token;
- pessoa;
- empresa;
- vínculo;
- papel;
- conta;
- dispositivo.

---

# 40. Banco de dados — modelo recomendado

## Pessoa

```text
pessoas
- id
- cpf
- nome
- email
- celular
- status
- created_at
```

## Empresa

```text
empresas
- id
- cnpj
- razao_social
- nome_fantasia
- porte
- regime
- status
```

## Conta

```text
contas
- id
- empresa_id / pessoa_id
- tipo
- agencia
- numero
- status
```

## Vínculo

```text
vinculos
- id
- pessoa_id
- empresa_id
- papel
- alçada
- status
- criado_por
- criado_em
```

## Dispositivo

```text
dispositivos
- id
- pessoa_id
- identificador
- nome
- confiavel
- bloqueado
- criado_em
- ultimo_acesso
```

## Auditoria

```text
auditoria
- id
- pessoa_id
- empresa_id
- ação
- recurso
- recurso_id
- data
- ip
- dispositivo
- resultado
```

---

# 41. Estado de operações

Evitar que um pagamento seja simplesmente:

```text
enviado
```

Usar estados:

```text
CRIADO
↓
EM_ANALISE
↓
AGUARDANDO_APROVACAO
↓
APROVADO
↓
PROCESSANDO
↓
CONCLUIDO
```

Ou:

```text
RECUSADO
CANCELADO
BLOQUEADO
ESTORNADO
```

Isso deixa o sistema muito mais realista.

---

# 42. Idempotência

Manter a correção já feita:

> idempotência por conta.

Não deixar uma mesma chave de idempotência de uma pessoa interferir em outra conta.

Isso é uma correção importante e deve permanecer.

---

# 43. Dinheiro

Manter:

```text
"1500.00"
```

na API.

Não usar `float` para dinheiro.

O frontend pode converter somente para exibição.

---

# 44. Postgres

O `HANDOFF.md` informa que a migração v7 ainda não foi validada em PostgreSQL real.

Antes de apresentar backend como "pronto":

- executar migration em Postgres;
- testar criação;
- testar login;
- testar vínculo;
- testar pagamento;
- testar aprovação;
- testar rollback;
- testar concorrência.

---

# 45. Biometria real

O `HANDOFF.md` informa que o fluxo DeepFace real ainda não foi exercitado completamente com câmera.

Antes de dizer:

> "Nossa biometria funciona"

confirmar:

- câmera real;
- iluminação;
- prova de vida;
- falso positivo;
- falso negativo;
- tempo de resposta;
- concorrência;
- erro de câmera;
- timeout.

Se não for possível testar antes da banca:

> apresentar como protótipo/simulação.

---

# 46. Modo demonstração

O modo demo atualmente permite que qualquer login desconhecido entre em uma conta de demonstração.

Isso é aceitável para roteiro de apresentação, mas **não pode parecer uma regra do banco**.

Adicionar claramente:

> **Modo demonstração**

ou:

> **Ambiente de apresentação**

Não deixar isso confundido com produção.

---

# 47. Credenciais de desenvolvimento

O README contém credencial administrativa de desenvolvimento.

Isso deve ser claramente:

```text
somente desenvolvimento
```

e nunca funcionar em produção.

Além disso:

- não colocar senha real no repositório;
- não colocar token real;
- rotacionar credenciais que tenham sido expostas;
- usar `.env`.

O `HANDOFF.md` já registra que um token da Expo foi exposto e precisa ser revogado manualmente. Isso deve ser tratado antes de uma apresentação pública do repositório.

---

# 48. Funcionalidades simuladas

Deixar explicitamente marcadas:

- Pix copia e cola simulado;
- boleto simulado;
- depósito de demonstração;
- cartão virtual, se não houver backend real;
- Pix Automático, se apenas o backend estiver pronto;
- webhooks, se não houver interface;
- integração de certificado;
- biometria stub.

Não esconder isso.

Uma banca de segurança tende a valorizar mais:

> "Aqui simulamos porque não temos integração com SPI/DICT."

do que:

> "Funciona."

quando não funciona de verdade.

---

# 49. O que NÃO precisa ser feito antes da banca

Não gastar tempo tentando implementar:

- SPI real;
- DICT real;
- emissão real de boleto;
- cartão de crédito real;
- integração bancária real;
- Receita Federal completa;
- sistema de RH completo;
- antifraude com machine learning;
- FGC real;
- infraestrutura de produção bancária.

Para a apresentação, o objetivo é **coerência arquitetural e experiência de uso**.

---

# 50. Prioridade para a apresentação

## P0 — obrigatório

### Lógica

- [ ] Corrigir onboarding PJ.
- [ ] Remover e-CNPJ como login cotidiano.
- [ ] Login PJ = pessoa + vínculo com empresa.
- [ ] CPF do usuário PJ.
- [ ] Representante legal na abertura.
- [ ] Usuários secundários.
- [ ] Papéis.
- [ ] Alçadas.
- [ ] Aprovação dupla.
- [ ] Dispositivo confiável.
- [ ] Revogação de dispositivo.
- [ ] Auditoria básica.

### Front

- [ ] Corrigir layout na moldura reduzida.
- [ ] Criar duplo clique para expandir celular.
- [ ] Fundo escuro/opaco no modo expandido.
- [ ] Criar tela de Equipe realmente funcional.
- [ ] Criar edição/revogação de usuário.
- [ ] Melhorar tela de aprovação.
- [ ] Melhorar onboarding PJ.
- [ ] Corrigir texto do certificado.
- [ ] Mostrar claramente PF x PJ.
- [ ] Mostrar conta/empresa atualmente selecionada.

---

# 51. P1 — importante

- [ ] Dispositivos confiáveis.
- [ ] Sessões.
- [ ] Notificações de segurança.
- [ ] Auditoria.
- [ ] Contestação no frontend.
- [ ] Estorno no frontend.
- [ ] Perfil de acesso separado de perfil de autorização.
- [ ] Confirmação de celular/e-mail.
- [ ] Step-up authentication.
- [ ] Recuperação de conta.
- [ ] Melhorar comprovante.

---

# 52. P2 — depois da apresentação

- [ ] Pix Automático no frontend.
- [ ] Pagamento em lote no frontend.
- [ ] Webhooks no frontend.
- [ ] DDA.
- [ ] Cartão de crédito.
- [ ] Caixinhas.
- [ ] Cashback.
- [ ] Postgres validado completamente.
- [ ] Biometria DeepFace calibrada.
- [ ] APK validado em aparelho físico.
- [ ] Armazenamento seguro do token no Android.
- [ ] Integrações externas reais.

---

# 53. Fluxo final recomendado para demonstrar na banca

## PF

```text
Abrir conta
 ↓
CPF
 ↓
Dados pessoais
 ↓
Documento
 ↓
Prova de vida
 ↓
Credencial
 ↓
Conta criada
 ↓
Login
 ↓
Home PF
```

## PJ

```text
Abrir conta
 ↓
CNPJ
 ↓
Dados da empresa
 ↓
Representante legal
 ↓
CPF
 ↓
Documentos
 ↓
Beneficiário final
 ↓
Prova de vida
 ↓
KYC/KYB
 ↓
Conta PJ
 ↓
Representante entra
 ↓
Equipe & permissões
 ↓
Adiciona funcionário
 ↓
Define papel + alçada
 ↓
Funcionário ativa sua própria credencial
 ↓
Funcionário entra
 ↓
Sistema verifica vínculo
 ↓
Sistema verifica permissões
 ↓
Sistema mostra somente o que ele pode usar
```

## Pagamento PJ

```text
Operador
 ↓
Cria pagamento
 ↓
Servidor verifica:
- conta
- vínculo
- papel
- alçada
- dispositivo
- limite
- risco
 ↓
Dentro da alçada?
 ├─ SIM → continua
 └─ NÃO → aprovação
              ↓
          Aprovador
              ↓
          autenticação
              ↓
            aprova
              ↓
           execução
```

---

# 54. Conceitos de Cibersegurança para destacar na banca

O projeto pode demonstrar:

### IAM

Identity and Access Management.

### RBAC

Role-Based Access Control.

Exemplo:

```text
Administrador
Aprovador
Operador
Consulta
```

### Least Privilege

Cada pessoa recebe somente o acesso necessário.

### Separation of Duties

Quem cria uma operação não precisa ser quem aprova.

### MFA

Mais de um fator para autenticação.

### Device Trust

Dispositivo cadastrado/confiável.

### Step-up Authentication

Autenticação adicional quando uma operação exige maior segurança.

### Risk-Based Authentication

A autenticação/controle muda de acordo com o risco.

### Audit Trail

Registro das ações.

### Idempotency

Evita duplicação de operações.

### Server-Side Authorization

O backend é a autoridade final das permissões.

---

# 55. Resultado esperado

Ao terminar essas mudanças, a lógica do Astro deverá ser entendida assim:

```text
                    ASTRO
                      │
          ┌───────────┴───────────┐
          │                       │
         PF                      PJ
          │                       │
      Pessoa                   Empresa
          │                       │
      Conta PF                Conta PJ
                                  │
                         ┌────────┴────────┐
                         │                 │
                    Representante      Usuários
                                          │
                              ┌───────────┼───────────┐
                              │           │           │
                            Admin      Operador    Consulta
                              │           │
                              │        Alçada
                              │           │
                              └──────┬────┘
                                     ↓
                                Pagamento
                                     ↓
                              Motor de risco
                                     ↓
                         ┌───────────┴───────────┐
                         │                       │
                       Normal                  Alto
                         │                       │
                      Executa            MFA / aprovação
                                                 │
                                              Executa
```

O mais importante é que **a segurança não fique representada por uma única tecnologia**, como facial ou certificado digital.

A segurança do Astro deve ser apresentada como **defesa em profundidade**:

```text
Identidade
   +
Autenticação
   +
Dispositivo
   +
Permissões
   +
Alçada
   +
Limites
   +
Risco
   +
Aprovação
   +
Auditoria
```

---

# 56. Referências utilizadas na revisão

- Banco Central do Brasil — Segurança no Pix.
- Banco Central do Brasil — cadastro de dispositivos e limites.
- Santander Empresas — Usuário Master, Usuário Secundário, perfis de acesso e perfis de autorização.
- Santander Empresas — gerenciamento de usuários.
- Receita Federal — perfis de representação de pessoa jurídica.
- Documentação atual do próprio repositório Astro (`README.md`, `HANDOFF.md` e `PLANO.md`).

> As regras bancárias reais devem ser tratadas como referência de produto e segurança, não como uma tentativa de reproduzir internamente toda a infraestrutura regulatória e operacional de um banco real.

# 52. ARQUITETURA DE API — REST, Full Stack e evolução

## Recomendação para o Astro

**Manter REST + FastAPI + React/TypeScript/Capacitor.** Não vale trocar o projeto para uma arquitetura full-stack acoplada.

Fluxo recomendado:

```text
React / Capacitor
       |
       | HTTPS + JSON
       v
FastAPI REST /api/v1
       |
       +--> Auth
       +--> Accounts
       +--> Companies
       +--> Payments
       +--> Pix
       +--> Approvals
       +--> KYC
       +--> Security
       |
       v
PostgreSQL
```

O frontend nunca deve falar diretamente com PostgreSQL, Receita Federal, Serpro ou fornecedor de biometria.

### REST x "Full Stack"

REST é o melhor encaixe porque o Astro já possui frontend separado, backend separado e possibilidade de app mobile. A mesma API pode atender:

```text
Web
Mobile
Site/serviços internos
futuras integrações
```

O backend deve ser um **monólito modular**, não dezenas de microserviços. Microserviços só devem aparecer quando houver necessidade real de escala, isolamento ou equipes independentes.

### Versionamento

Criar desde já:

```text
/api/v1/
```

Exemplos:

```text
GET  /api/v1/accounts
GET  /api/v1/transactions
POST /api/v1/transfers
POST /api/v1/pix
GET  /api/v1/companies/{id}/members
POST /api/v1/companies/{id}/members
POST /api/v1/approvals/{id}/approve
```

---

# 53. Como organizar o FastAPI

A regra deve ser:

> **endpoint recebe a requisição; service executa a regra; repository acessa o banco.**

Estrutura sugerida:

```text
backend/
  app/
    api/
      v1/
        auth.py
        users.py
        accounts.py
        companies.py
        members.py
        payments.py
        pix.py
        approvals.py
        kyc.py
        devices.py
        security.py

    services/
      auth_service.py
      payment_service.py
      identity_service.py
      kyc_service.py
      fraud_service.py
      notification_service.py

    repositories/
      users.py
      accounts.py
      companies.py
      transactions.py

    models/
    schemas/
    core/
```

Evitar concentrar tudo em `routes.py` ou colocar regra de negócio dentro do componente React.

---

# 54. Padrão de erros da API

Padronizar respostas de erro usando `application/problem+json`, conforme RFC 9457.

Exemplo:

```json
{
  "type": "https://api.astro.local/problems/insufficient-funds",
  "title": "Saldo insuficiente",
  "status": 422,
  "detail": "A conta não possui saldo disponível para concluir a operação.",
  "code": "INSUFFICIENT_FUNDS",
  "request_id": "req_01..."
}
```

Não retornar mensagens inconsistentes como:

```json
{"error": "deu ruim"}
```

---

# 55. Idempotência financeira

Toda operação financeira importante deve aceitar uma chave de idempotência:

```http
POST /api/v1/transfers
Idempotency-Key: 7d1b...
```

Se o usuário clicar duas vezes, a segunda requisição deve recuperar o resultado da primeira em vez de criar uma segunda transferência.

Aplicar a:

- transferência;
- Pix;
- pagamento;
- cobrança;
- estorno;
- aprovação;
- lote.

---

# 56. Estado das transações

Não modelar operação apenas como `success/failure`.

Usar estados, por exemplo:

```text
CREATED
  ↓
PENDING_RISK
  ↓
PENDING_APPROVAL
  ↓
AUTHORIZED
  ↓
PROCESSING
  ↓
COMPLETED
```

E estados de exceção:

```text
REJECTED
CANCELLED
EXPIRED
FAILED
REVERSED
CONTESTED
```

Isso é particularmente importante para Pix, split, aprovação e estorno.

---

# 57. CPF — API oficial e o que realmente é possível

Existe solução oficial para consulta de CPF por API. A Receita Federal disponibiliza a solução de consulta de dados cadastrais e o Serpro fornece o produto **Consulta CPF**.

**Não tratar isso como uma API pública gratuita que qualquer frontend pode chamar.** É uma integração autenticada/contratada.

Em 2026, a Consulta CPF V3 passou a exigir:

```text
CPF + data de nascimento
```

O Serpro informa que a V3 utiliza OAuth 2.0 e credenciais de cliente. As credenciais devem permanecer exclusivamente no backend.

Arquitetura correta:

```text
React
  |
  v
FastAPI
  |
  v
Identity Service
  |
  v
Serpro Consulta CPF
  |
  v
Receita Federal
```

Nunca:

```text
React -> Serpro com Consumer Secret
```

---

# 58. CPF não é KYC completo

Uma consulta de CPF pode confirmar situação cadastral e correspondência de dados, mas isso não prova sozinha que a pessoa diante da câmera é a titular.

Para um fluxo de identidade mais forte:

```text
CPF
+
data de nascimento
+
documento
+
selfie
+
liveness
+
face match
```

O frontend só recebe o resultado necessário:

```json
{
  "verified": true,
  "status": "REGULAR"
}
```

Não deve receber credenciais ou detalhes internos do fornecedor.

---

# 59. CNPJ / KYB

Para PJ, separar:

```text
CNPJ
  ↓
validação cadastral da empresa
  ↓
representante
  ↓
CPF do representante
  ↓
relação/representação
  ↓
documentos
  ↓
KYB
```

Não fazer:

```text
CNPJ digitado -> acesso administrativo automático
```

A empresa é uma entidade e os usuários são pessoas vinculadas a ela.

---

# 60. RG, CIN e documentos brasileiros

Não criar uma falsa "API federal universal de RG".

O RG tradicional é descentralizado pelos estados. O Brasil está migrando para a **Carteira de Identidade Nacional (CIN)**.

A CIN possui QR Code e existe serviço oficial para verificar sua emissão/validade. A leitura completa oficial permite comparar dados da CIN, e o serviço exige conexão e conta gov.br para a modalidade completa.

Para o Astro:

```text
CIN
 |
QR Code
 |
validação
 |
comparação de dados
```

é conceitualmente melhor que assumir que qualquer número de RG pode ser consultado em uma única base federal.

---

# 61. Documento: OCR não é validação

Separar claramente:

```text
OCR
```

de:

```text
document verification / documentoscopia
```

OCR apenas extrai texto.

Pipeline de protótipo:

```text
foto do documento
      ↓
OpenCV
      ↓
correção de perspectiva
      ↓
PaddleOCR
      ↓
campos estruturados
      ↓
validação de formato
      ↓
comparação com cadastro
```

Para produção, usar serviço especializado de verificação documental quando necessário.

---

# 62. Biblioteca para OCR

Para o protótipo do Astro, uma combinação interessante é:

```text
OpenCV + PaddleOCR
```

Alternativas:

```text
Tesseract
EasyOCR
```

Mas nenhum OCR deve ser apresentado como prova de autenticidade do documento.

---

# 63. Reconhecimento facial: separar três problemas

Não confundir:

### Face detection

```text
Existe um rosto na imagem?
```

### Face verification / recognition

```text
Este rosto corresponde à identidade cadastrada?
```

### Liveness / anti-spoofing

```text
É uma pessoa real diante da câmera ou uma foto/vídeo/tela?
```

Para KYC, o fluxo ideal é:

```text
documento
   +
selfie
   +
liveness
   +
face match
```

---

# 64. Melhor biblioteca facial para o Astro

## Para facilidade de implementação: DeepFace

O **DeepFace** é interessante para o projeto acadêmico porque simplifica comparação facial, escolha de modelos e detectores, e possui opção de anti-spoofing.

É a escolha mais simples se o objetivo for:

> colocar uma prova de conceito funcionando rapidamente.

## Para maior controle técnico: InsightFace

O **InsightFace** é uma opção mais avançada para controlar detecção, embeddings, ArcFace e inferência local. A implementação atual do projeto também possui servidor com API REST e recursos de comparação/registro e verificações de liveness.

### Atenção à licença

Não assumir que "GitHub + MIT" significa que todos os modelos pré-treinados podem ser usados comercialmente. O próprio InsightFace diferencia licença do código e licença dos modelos.

Para uma banca acadêmica:

```text
DeepFace / InsightFace
```

é aceitável como protótipo, desde que a documentação deixe claro o caráter experimental e as licenças sejam respeitadas.

Para produção bancária:

```text
fornecedor especializado
+
SLA
+
compliance
+
licença
+
antifraude
```

é mais apropriado.

---

# 65. Liveness: protótipo x produção

O Astro já possui um conceito de desafio facial. Manter e melhorar:

```text
challenge_id
nonce
expected_action
expires_at
attempts
device_id
```

Exemplo:

```text
Challenge: 83a...
Ação: virar para a direita
Expira: 30 segundos
Tentativas: 1/3
```

Para uma implementação real, uma biblioteca facial local simples não deve ser tratada como equivalente a uma solução profissional de prova de vida.

Duas referências importantes:

- **Amazon Rekognition Face Liveness** possui APIs específicas para criação de sessão e obtenção do resultado.
- **Serpro Datavalid V4** oferece validação biográfica, biometria facial com ou sem prova de vida, impressão digital e validação de QR Code da CNH.

Portanto:

```text
PROTÓTIPO
DeepFace/OpenCV + challenge

PRODUÇÃO BRASILEIRA
Datavalid / fornecedor KYC especializado
```

---

# 66. "Faceless": não fazer reconhecimento facial a cada login

Se a ideia é permitir acesso sem rosto em todas as sessões, o modelo pode ser:

```text
ONBOARDING
CPF + documento + selfie + liveness
          ↓
identidade verificada

LOGIN NORMAL
senha/passkey + dispositivo

OPERAÇÃO DE ALTO RISCO
step-up + MFA/biometria/liveness quando necessário
```

Assim o rosto não vira a única credencial do usuário nem precisa ser capturado em todo acesso.

---

# 67. Biometria local x biometria no servidor

Separar:

### Biometria do dispositivo

O celular usa Face ID/biometria do próprio sistema para desbloquear uma credencial/passkey.

### Biometria KYC

O banco/fornecedor compara uma selfie com uma referência para verificar identidade e pode executar prova de vida.

São problemas diferentes.

A documentação do Astro deve usar termos como:

```text
verificação de identidade
reconhecimento facial
prova de vida
```

em vez de chamar tudo simplesmente de "biometria".

---

# 68. Modelo de dados para KYC

Criar conceitos separados:

```text
kyc_cases
-----------
id
user_id
status
risk_level
created_at
completed_at

identity_documents
------------------
id
kyc_case_id
type
status
storage_ref
expires_at

biometric_verifications
-----------------------
id
kyc_case_id
provider
type
status
score
challenge_id
created_at
```

Não misturar documento, selfie e autenticação em uma única coluna da tabela de usuário.

---

# 69. LGPD e biometria

Biometria facial é dado pessoal sensível. O Astro deve tratá-la como dado de alta criticidade.

Não guardar indefinidamente:

```text
selfie.jpg
```

sem uma finalidade clara.

A arquitetura deve definir:

- finalidade;
- acesso;
- retenção;
- segurança;
- auditoria;
- exclusão quando aplicável;
- base legal adequada.

Como projeto acadêmico, isso deve ser apresentado como desenho técnico e não como parecer jurídico.

---

# 70. Provider abstraction — um dos upgrades mais importantes

Não colocar integrações externas diretamente na regra de negócio.

Criar interfaces:

```text
providers/
  cpf/
    base.py
    mock.py
    serpro.py

  identity/
    base.py
    mock.py
    datavalid.py

  face/
    base.py
    mock.py
    deepface.py
```

A regra de negócio chama:

```python
cpf_provider.verify(...)
```

e não:

```python
if DEMO:
    ...
else:
    requests.post("https://serpro...")
```

espalhado pelo sistema.

Isso permite trocar o fornecedor sem reescrever o fluxo inteiro.

---

# 71. API interna de identidade

Criar endpoints internos/externos controlados como:

```http
POST /api/v1/identity/cpf/verify
POST /api/v1/identity/documents
POST /api/v1/identity/face/challenges
POST /api/v1/identity/face/verify
```

### Exemplo CPF

```json
{
  "cpf": "...",
  "birth_date": "..."
}
```

O frontend não precisa saber se a resposta veio de:

```text
Mock
Serpro
outro fornecedor
```

---

# 72. Upload de documentos

Validar no backend:

- tamanho;
- MIME real;
- magic bytes;
- extensão;
- dimensões;
- conteúdo;
- quantidade de tentativas.

Não confiar apenas em:

```text
filename
Content-Type
```

Documentos devem ficar em armazenamento privado, não em `/uploads` publicamente acessível.

---

# 73. Segurança da API — OWASP

O Astro deve ser testado contra o OWASP API Security Top 10, especialmente:

1. Broken Object Level Authorization (BOLA/IDOR)
2. Broken Authentication
3. Broken Object Property Level Authorization
4. Unrestricted Resource Consumption
5. Broken Function Level Authorization
6. Unrestricted Access to Sensitive Business Flows
7. SSRF
8. Security Misconfiguration
9. Improper Inventory Management
10. Unsafe Consumption of APIs

Os pontos mais críticos para o Astro são:

```text
BOLA
Autenticação
Autorização por função
Autorização por propriedade
Abuso de fluxos financeiros
APIs externas
```

---

# 74. Autorização por objeto

Nunca fazer apenas:

```python
transaction = get_transaction(transaction_id)
```

e devolver o resultado.

O servidor precisa verificar:

```text
usuário
+
sessão
+
dispositivo
+
empresa selecionada
+
vínculo
+
permissão
+
objeto solicitado
```

Exemplo conceitual:

```python
if transaction.account_id not in authorized_accounts:
    raise Forbidden()
```

Isso combate uma das categorias mais importantes do OWASP API Security Top 10: BOLA.

---

# 75. Rate limiting

Usar limites diferentes por endpoint.

```text
/login              -> baixo
/forgot-password    -> muito baixo
/face-verification  -> baixo + caro
/transfer           -> limitado
/pix                -> limitado + risco
```

Biometria e recuperação de conta merecem proteção especial porque podem ser abusadas por automação.

---

# 76. Antifraude baseado em risco

Não inventar uma "IA antifraude" apenas para a apresentação.

Começar com regras:

```text
novo dispositivo
+
novo destinatário
+
valor alto
+
horário incomum
+
muitas tentativas
```

gera um contexto de risco:

```text
normal
step-up
review
block/hold
```

Os limiares devem ser parâmetros internos do protótipo e não apresentados como regra oficial do Banco Central.

---

# 77. Step-up authentication

Não exigir a mesma autenticação para qualquer ação.

```text
ver extrato
  -> sessão normal

adicionar beneficiário
  -> MFA

alterar limite
  -> MFA/biometria

transferência alta
  -> step-up + risco

administrar equipe
  -> step-up quando necessário
```

---

# 78. Dispositivo confiável

Manter o conceito atual de `X-Dispositivo-Id`, mas evoluir o modelo para:

```text
device
------
id
user_id
platform
name
status
registered_at
last_seen_at
risk_level
```

Frontend:

```text
Segurança > Dispositivos

Chrome - Windows
Confiável
Último acesso: agora

Android
Confiável
Último acesso: ontem

[Revogar]
```

---

# 79. Sessões

Criar tela de sessões ativas:

```text
Chrome Windows
São Paulo
Agora

Android
Ontem

[Encerrar todas]
```

O backend precisa permitir revogar sessão/dispositivo.

---

# 80. Auditoria

Criar `audit_events`.

Exemplo:

```text
Usuário: 123
Empresa: 456
Ação: CREATE_TRANSFER
Operação: 789
Valor: R$ 25.000
Dispositivo: 111
Resultado: PENDING_APPROVAL
Timestamp: ...
```

Registrar pelo menos:

- login;
- falha de login;
- criação de usuário;
- mudança de permissão;
- mudança de alçada;
- novo dispositivo;
- Pix;
- transferência;
- aprovação;
- rejeição;
- estorno;
- contestação;
- revogação.

Nunca registrar senha, token, refresh token, secret, CVV ou template biométrico em log.

---

# 81. Concorrência financeira

Não depender apenas de Python para impedir dupla utilização de saldo.

Operações críticas devem usar transações de banco, locks ou updates atômicos conforme o caso.

Exemplo:

```text
Saldo = R$ 1.000

A tenta gastar R$ 800
B tenta gastar R$ 800
```

As duas não podem ser aprovadas simplesmente porque cada requisição leu o mesmo saldo inicial.

---

# 82. Webhooks

Webhook externo deve ser tratado como entrada não confiável.

Validar:

```text
assinatura
timestamp
nonce/idempotência
schema
```

Não aceitar simplesmente:

```http
POST /webhook

{"status":"paid"}
```

sem autenticação/verificação.

---

# 83. APIs externas

Serpro, Datavalid, OCR, biometria e outros fornecedores devem ser tratados como integrações externas.

Usar:

```text
timeout
retry controlado
schema validation
logs
request_id
circuit breaker (futuro)
```

Nunca deixar uma API externa travar indefinidamente o backend.

---

# 84. Frontend não decide segurança

O React pode esconder um botão:

```typescript
if (!canApprove) hideButton()
```

Mas isso é apenas UX.

A API ainda precisa rejeitar:

```http
POST /api/v1/approvals/123/approve
```

se o usuário não possuir autorização.

---

# 85. Login PJ — correção definitiva

O frontend atual não deve apresentar:

```text
Entrar com certificado digital
```

como login diário de PME/Grande empresa.

O fluxo deve ser:

```text
CPF/e-mail
+
credencial da pessoa
      ↓
contas/vínculos disponíveis
      ↓
selecionar empresa
```

O certificado digital pode existir como:

```text
assinatura
integração empresarial
integração fiscal
operação específica
```

mas não como identidade compartilhada de toda a equipe.

---

# 86. PJ onboarding definitivo

```text
CNPJ
  ↓
dados da empresa
  ↓
representante legal
  ↓
CPF do representante
  ↓
validação cadastral
  ↓
documentos
  ↓
selfie + liveness
  ↓
KYB/KYC
  ↓
conta PJ
  ↓
administrador
  ↓
convites para equipe
```

O rosto do representante comprova a identidade do representante no onboarding; ele não vira automaticamente a autenticação de todos os funcionários.

---

# 87. PF onboarding definitivo

```text
Nome
CPF
Data de nascimento
E-mail
Celular
   ↓
CPF check
   ↓
documento
   ↓
selfie
   ↓
liveness
   ↓
face match
   ↓
conta
   ↓
dispositivo
```

---

# 88. "Sem rosto" depois do onboarding

O usuário não deve precisar fazer selfie toda vez que abrir o app.

Modelo recomendado:

```text
Onboarding
  -> identidade forte

Login normal
  -> senha/passkey + dispositivo

Operação de risco
  -> step-up
```

Isso melhora simultaneamente UX e segurança.

---

# 89. Senhas e credenciais

Usar hash de senha moderno, preferencialmente Argon2id através de biblioteca madura.

Nunca:

```text
senha em plaintext
SHA256(password) sozinho
senha fixa no código
```

Segredos externos devem ficar em `.env` apenas no desenvolvimento e em secret manager/cofre em produção.

---

# 90. Passkeys / WebAuthn

Adicionar como evolução de autenticação forte:

```text
Usuário
   |
Passkey
   |
chave privada no autenticador
   |
servidor guarda chave pública
```

Vantagens:

- resistência maior a phishing;
- credencial individual;
- bom encaixe com mobile;
- não exige compartilhar senha entre pessoas.

Não é necessário bloquear a banca para implementar isso; pode ser P2.

---

# 91. OCR + documento + rosto — fluxo completo

O melhor desenho para o Astro é:

```text
              DOCUMENTO
                  |
                  v
             OCR / QR
                  |
                  v
          dados extraídos
                  |
                  v
        validação documental
                  |
                  +----------------+
                                   |
SELFIE --> LIVENESS --> FACE MATCH
                                   |
                                   v
                            identidade OK?
                                   |
                              +----+----+
                              |         |
                             SIM       NÃO
                              |         |
                              v         v
                            KYC       REJEITAR
```

---

# 92. Integrações oficiais: como documentar

No README/HANDOFF, usar três estados:

```text
IMPLEMENTADO
SIMULADO
PLANEJADO
```

Exemplo:

```text
CPF Serpro: PLANEJADO/INTEGRÁVEL
OCR: IMPLEMENTADO/PROTÓTIPO
Liveness: PROTÓTIPO
Pix: SIMULADO
SPI/DICT: NÃO INTEGRADO
```

Isso é muito mais profissional que dizer que uma integração existe quando ela está apenas mockada.

---

# 93. O que NÃO fazer antes da banca

Não gastar o tempo restante com:

- SPI real;
- DICT real;
- cartão real;
- boleto real;
- microserviços;
- Kubernetes;
- ML antifraude complexo;
- sistema completo de RH;
- toda a infraestrutura bancária de produção;
- integração governamental completa sem contrato.

Priorizar coerência, segurança e demonstração.

---

# 94. Prioridade nova — P0

## Backend

- [ ] `/api/v1`;
- [ ] autorização por objeto;
- [ ] idempotência financeira;
- [ ] estados de transação;
- [ ] validação de alçada no backend;
- [ ] aprovação separada;
- [ ] request ID;
- [ ] erros padronizados;
- [ ] rate limit básico;
- [ ] testes de autorização.

## Identidade

- [ ] corrigir PF/PJ;
- [ ] CPF + nascimento;
- [ ] documento como etapa separada;
- [ ] liveness separado de face match;
- [ ] provider abstraction;
- [ ] não usar e-CNPJ como login diário.

## Front

- [ ] equipe completa;
- [ ] permissões;
- [ ] alçadas;
- [ ] pendentes;
- [ ] dispositivos;
- [ ] sessões;
- [ ] KYC visual;
- [ ] modo expandido.

---

# 95. Prioridade P1

- [ ] PostgreSQL real;
- [ ] migrations testadas;
- [ ] audit log;
- [ ] upload privado;
- [ ] OCR;
- [ ] mock CPF provider;
- [ ] mock identity provider;
- [ ] testes de liveness com câmera;
- [ ] recovery;
- [ ] notificações;
- [ ] webhooks;
- [ ] documentação OpenAPI.

---

# 96. Prioridade P2

- [ ] Serpro Consulta CPF real;
- [ ] Datavalid;
- [ ] document verification;
- [ ] Passkeys/WebAuthn;
- [ ] Redis;
- [ ] filas;
- [ ] tracing;
- [ ] circuit breaker;
- [ ] antifraude avançado;
- [ ] secret manager;
- [ ] object storage privado.

---

# 97. Stack recomendada

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
PostgreSQL
pytest
```

## Face — protótipo

```text
DeepFace
OpenCV
```

## Face — mais avançado

```text
InsightFace
ArcFace
ONNX Runtime
liveness separado
```

## Documento

```text
OpenCV
PaddleOCR
```

## Front

```text
React
TypeScript
Vite
TanStack
Capacitor
```

## Segurança

```text
Argon2id
RBAC
alçadas
MFA
passkeys (futuro)
device binding
rate limiting
idempotency
audit log
```

---

# 98. Arquitetura final

```text
                    ┌─────────────────────────┐
                    │ React / Capacitor       │
                    │ Astro App               │
                    └────────────┬────────────┘
                                 │ HTTPS
                                 v
                    ┌─────────────────────────┐
                    │ FastAPI REST /api/v1    │
                    │                         │
                    │ Auth / Accounts / PJ    │
                    │ Payments / Pix          │
                    │ Approvals / Security    │
                    │ KYC / Identity          │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴────────────────┐
                 v                                v
       ┌─────────────────┐              ┌────────────────────┐
       │ PostgreSQL      │              │ Provider Layer     │
       │                 │              │                    │
       │ users           │              │ CPF / CNPJ         │
       │ companies       │              │ Identity           │
       │ accounts        │              │ Face / Liveness    │
       │ transactions    │              │ OCR                │
       │ devices         │              └─────────┬──────────┘
       │ approvals       │                        │
       │ audit_events    │              ┌─────────┼─────────┐
       └─────────────────┘              v         v         v
                                      Serpro   Datavalid  Face/OCR
```

---

# 99. Fluxo de segurança que a banca deve conseguir entender

```text
IDENTIDADE
    ↓
AUTENTICAÇÃO
    ↓
CONTA / EMPRESA
    ↓
PERMISSÃO
    ↓
ALÇADA
    ↓
RISCO
    ↓
STEP-UP
    ↓
APROVAÇÃO
    ↓
IDEMPOTÊNCIA
    ↓
PROCESSAMENTO
    ↓
AUDITORIA
    ↓
NOTIFICAÇÃO
```

Esse é o fluxo que deve aparecer por trás da interface.

---

# 100. Fontes técnicas consultadas nesta ampliação

As fontes abaixo foram usadas para validar as partes que envolvem serviços atuais, APIs oficiais e bibliotecas.

### Governo / identidade

- Receita Federal / Gov.br — solução de consulta de dados de CPF por API.
- Serpro — Consulta CPF V3, lançada em 2026, com CPF + data de nascimento e OAuth 2.0.
- Serpro — Datavalid V4, com validações biográficas, biometria facial com ou sem prova de vida e QR Code da CNH.
- Gov.br / Governo Digital — carteira de documentos digitais.
- Gov.br / Ministério da Justiça — validação do QR Code da CIN.
- Banco Central — camadas de segurança do Pix.

### Segurança de API

- OWASP API Security Top 10 2023.
- RFC 9457 — Problem Details for HTTP APIs.

### Biometria

- DeepFace — comparação facial e opção de anti-spoofing.
- InsightFace — reconhecimento facial, ArcFace e servidor/API; atenção às licenças dos modelos.
- Amazon Rekognition Face Liveness — APIs específicas de prova de vida.

---

# 101. Links de referência

- Consulta CPF / Receita Federal: `gov.br/pt-br/servicos/obter-solucao-de-consulta-de-dados-de-cadastro-de-pessoa-fisica-cpf`
- Serpro Consulta CPF V3: `centraldeajuda.serpro.gov.br/duvidas/pt/avisos/avisoconsultacpfv3/`
- Serpro Datavalid V4: `centraldeajuda.serpro.gov.br/duvidas/pt/avisos/avisodatavalidv4/`
- Validação da CIN: `gov.br/pt-br/servicos/verificar-validade-de-qr-code-da-carteira-de-identidade-nacional`
- Segurança do Pix: `bcb.gov.br/estabilidadefinanceira/pix-seguranca`
- OWASP API Security: `api-security.owasp.org/`
- RFC 9457: `rfc-editor.org/rfc/rfc9457`
- DeepFace: `github.com/serengil/deepface`
- InsightFace: `github.com/deepinsight/insightface`
- Amazon Rekognition Face Liveness: `docs.aws.amazon.com/rekognition/latest/dg/face-liveness-calling-apis.html`

---

# 102. Conclusão da revisão

O Astro não precisa virar um banco real para ser tecnicamente convincente.

O que precisa ser convincente é a cadeia:

```text
Pessoa
  ↓
Identidade
  ↓
Credencial
  ↓
Conta
  ↓
Vínculo PJ
  ↓
Permissão
  ↓
Alçada
  ↓
Risco
  ↓
Autenticação forte
  ↓
Aprovação
  ↓
Transação
  ↓
Auditoria
```

A combinação recomendada para o estágio atual é:

```text
FastAPI REST /v1
+
PostgreSQL
+
React/TypeScript/Capacitor
+
DeepFace/OpenCV para protótipo facial
+
PaddleOCR para OCR
+
providers abstratos para CPF/KYC
+
RBAC + alçadas
+
device binding
+
idempotência
+
audit log
+
OWASP API Security
```

Para produção, substituir os componentes experimentais por integrações oficiais/contratadas e fornecedores especializados de identidade, documentoscopia, liveness e antifraude.

> **Regra central do Astro:** a empresa possui a conta; a pessoa possui a credencial; o vínculo define o que a pessoa pode fazer.
