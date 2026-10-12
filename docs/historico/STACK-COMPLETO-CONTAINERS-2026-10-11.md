## Resultado

Cartão: atualizar a versão do GitHub e executar o app completo em containers.
Status: concluído para execução local de frontend, API e PostgreSQL.
Commits: base atualizada por fast-forward de 4001e89 para ace994b; correções desta etapa ainda locais, sem commit ou push.
Arquivos alterados: README.md; docker-compose.full.yml; app/Dockerfile; app/nginx.conf; app/scripts/cabecalhos-container.mjs e .d.mts; app/src/lib/cabecalhos-container.test.ts; backend/Dockerfile; este relatório.
Testes: 13 testes de configuração/CSP passaram; TypeScript, ESLint dos arquivos JS/TS e git diff --check aprovados. Build completo das imagens aprovado, incluindo leitura/hashes dos quatro modelos faciais como usuário não privilegiado. Nginx -t aprovado. Frontend, API e PostgreSQL saudáveis; migração terminou com código 0. Auditoria de runtime e conciliação executadas dentro do container, ambas aprovadas.
O que NÃO foi feito e por quê: nenhum deploy Azure, publicação no Docker Hub ou push GitHub nesta etapa. Não foi realizada prova de vida com câmera física; a disponibilidade dos modelos e o transporte DPoP foram verificados. O site institucional separado em site/ não faz parte do stack do aplicativo de pagamentos.
Problemas que vi fora do escopo: o compose.hub usa biometria stub e DPoP relaxado; o perfil testado aqui não usa esses ajustes. Dependências externas da câmera no navegador ainda vêm de CDN/Google Storage e exigem acesso à internet. O banco mantido é o volume já existente do Compose, sem importar automaticamente dados de outro banco nativo.
Como testar na mão:

1. Configurar os arquivos privados .env e .env.docker, sem enviá-los ao Git.
2. Executar `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.full.yml up -d --build`.
3. Abrir `http://localhost:8080`; API em `http://localhost:8000`.
4. Conferir `ps -a` usando os mesmos arquivos Compose: app, backend e db saudáveis; migrate encerrado com 0.
5. Cadastro/login facial com câmera física deve ser conferido pelo usuário. Pix e depósito continuam sendo simulação, com API real e dados persistidos em PostgreSQL.
6. Para parar preservando dados, usar `down` com os mesmos arquivos e sem `-v`.

Acesso ao GitHub inicialmente indisponível; nova tentativa funcionou e trouxe cinco commits novos. Foram incorporados os Dockerfiles do frontend/PostgreSQL, o Compose por imagens, os scripts de instalação e a correção de ordem dos scripts do frontend. Esta execução usa build do código local.

Correções verificadas:

- Modelos faciais baixados por mkstemp tinham permissão 0600. O chmod que retirava escrita deixava os arquivos inacessíveis ao usuário da API. O Dockerfile agora acrescenta leitura para esse usuário, mantém arquivos sem escrita e valida os hashes após USER astro. O erro real de permission denied foi reproduzido antes e a leitura de todos os modelos passou depois.
- CSP do nginx agora deriva do shell final, com hashes dos scripts inline, origens específicas para MediaPipe e wasm-unsafe-eval. Não usa script-src unsafe-inline nem connect-src *. Assets também recebem os cabeçalhos de segurança. Produção continua exigindo HTTPS; HTTP no perfil development só aceita API em loopback.
- O perfil completo adiciona o frontend, ajusta a origem pública da API/CORS e mantém DPoP obrigatório e biometria sem stub. API e frontend têm healthchecks; o frontend espera a API saudável. Banco sem porta publicada; containers de app/API sem capacidades adicionais e com filesystem somente leitura.

Verificação com Chromium real:

- Tela /login renderizou, sem tela branca e sem erro JavaScript.
- O formulário enviou credenciais fictícias à API real e recebeu 401; não aceitou login por mock.
- WebCrypto gerou prova ES256/DPoP e o navegador realizou login administrativo (200), consulta autenticada (200) e logout (204), sem imprimir tokens ou credenciais.
- CORS foi exercitado pelo navegador na origem localhost:8080.
- /, /login e /criar-conta responderam 200 com CSP; /saude e /pronto da API responderam 200.
- Screenshot da tela pública de login guardado fora do Git em /home/kali/.local/state/payment-platform-demo/app-container-login.png. O app foi aberto no navegador gráfico da VM com xdg-open.
