# Cadastro: celular e identidade única

O celular aceita DDD brasileiro válido e nove dígitos começando por 9. A interface
limita e formata a digitação como `(11) 98765-4321`; a API também valida e grava
`+5511987654321`. Telefone fixo, DDD inexistente, letras, dígitos Unicode e números
curtos/longos são recusados. Validação de formato não confirma existência ou posse;
isso requer verificação por SMS ou outro canal externo.

Referência: [Anatel — nono dígito](https://www.gov.br/anatel/pt-br/regulado/numeracao/codigos-nacionais/nono-digito).

CPF e CNPJ têm unicidade no banco e são normalizados antes do cadastro. A migração
`d71a9f04c2b8` acrescenta restrições de formato canônico para impedir variações que
contornem a unicidade, incluindo CPF com caracteres Unicode. Celular também tem
restrição de formato. Dados anteriores não são apagados nem truncados: se houver
valores incompatíveis, a migração deve aguardar correção confirmada com o titular.

Depois da prova de vida, o novo template facial é comparado com os templates
cifrados existentes, inclusive de usuários inativos. A comparação usa o mesmo
motor/modelo e limiar de reconhecimento configurados no servidor. Uma correspondência
recusa o cadastro, mesmo com outro CPF/e-mail. A resposta de duplicidade é genérica,
sem identificar outra pessoa nem dizer qual dado causou o conflito.

A comparação e a criação da pessoa/carteira ocorrem sob um advisory lock transacional
no PostgreSQL. Assim, instâncias distintas não criam simultaneamente duas identidades
com o mesmo rosto. O lock Python é complementar e suficiente apenas para SQLite em
um processo de desenvolvimento. Templates continuam cifrados; não foi criada uma
coluna pública com vetores ou fotos. O scan de templates é linear: volume/latência
precisam ser medidos antes de aumentar a base.

Um template indecifrável, inválido ou de outro modelo bloqueia o novo cadastro até
conferência; não é ignorado silenciosamente. Modelos biométricos são probabilísticos:
falsos positivos/negativos exigem avaliação física e revisão pelo suporte.

## Desenvolvimento e contas antigas

`BIOMETRIA_STUB=1` simula o reconhecimento, gerando o mesmo vetor artificial para
qualquer pessoa. Esse vetor não pode demonstrar identidade facial nem unicidade.

Para testar novos cadastros reais conservando o login das contas fictícias:
`BIOMETRIA_STUB=1` e `BIOMETRIA_STUB_CADASTRO=0`. É a configuração desta demonstração
local. A prova de vida e o reconhecimento dos **novos cadastros** são reais; o login
permanece simulado. Contas antigas com modelo `stub` não têm rosto real registrado,
e não participam da comparação em desenvolvimento. É necessário capturar/verificar
seus rostos por um fluxo apropriado antes de incluí-las nessa proteção.

Em produção qualquer stub é proibido. Templates legados de outro modelo/`stub`
exigem regularização; não liberam novos cadastros sem a conferência completa.

## Validação

Testes de API verificam números inválidos, CPF pontuado/Unicode, rostos próximos,
rostos distintos e template corrompido. Testes SQL confirmam recusa de gravações
fora do formato. Um teste com processos independentes no PostgreSQL prova a
serialização do cadastro facial. O navegador confirmou limite/máscara e bloqueio
do DDD inválido antes de abrir a câmera. Os modelos SFace, YuNet, anti-spoofing e
MediaPipe carregaram localmente; isso não substitui teste físico com pessoas.

## Primeira sessão

A tela usa `POST /usuarios/cadastro-sessao`: a prova de vida do cadastro autoriza também a primeira sessão, sem outra captura. DPoP e a política de atestação são conferidos antes de criar a pessoa. Documento, unicidade e desafio continuam obrigatórios conforme a configuração. Nos acessos seguintes, `/auth/login` e `/auth/login/mfa` continuam exigindo senha e rosto. `/usuarios` permanece compatível com integrações que apenas criam a conta.
