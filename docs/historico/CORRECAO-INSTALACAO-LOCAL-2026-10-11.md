## Resultado

Cartão: corrigir os erros identificados nos commits 96599f4 e 497ff07.
Status: concluído para os problemas de instalação/configuração descritos na revisão.
Commits: base atualizada para 497ff07; correções desta etapa locais, sem commit ou push.
Arquivos alterados: docker-compose.full.yml, install.sh, gerar-segredos.sh, astro.sh, .env.docker.example, README.md, docs/PARA-O-TIME.md, backend/tests/test_instalacao_containers.py e este relatório. Relatório anterior de revisão preservado.
Testes: 11 testes passaram, incluindo a integração opt-in com dois processos Docker para persistência de template facial e assinatura JWT; resolução real do Compose em instalação limpa e rejeição de cada segredo ausente; instalação local/Hub, permissões, repetição idempotente e migração de configuração antiga. Bash/sh syntax checks e git diff --check aprovados.
O que NÃO foi feito e por quê: nenhuma publicação GitHub, Docker Hub ou Azure nesta etapa; nenhuma alteração de modelo ou schema; nenhuma prova facial com câmera física. Não há garantia de ausência de qualquer outro erro/vulnerabilidade no aplicativo.
Problemas que vi fora do escopo: tags :latest das imagens de apresentação ainda não comprovam correspondência com o commit do código. O perfil local corrigido usa build local e mantém os controles reais.
Como testar na mão:

1. Em instalação nova, executar ./install.sh --local; depois o comando Compose completo do README.
2. Conferir que os três serviços ficam saudáveis e o migrate encerra com 0; abrir http://localhost:8080.
3. Não apagar/regenerar .env.docker ao reiniciar. JWT_SECRET, EMBEDDING_KEY e ADMIN_SENHA persistem; o Compose recusa iniciar se faltarem.
4. Para apresentação, usar ./install.sh --hub e ./astro.sh up; esse perfil continua explicitamente separado do perfil local com controles reais.
5. Regressão local: RUN_CONTAINER_INTEGRATION=1 python -m pytest backend/tests/test_instalacao_containers.py, com imagem payment-platform-backend:latest construída e Docker acessível.

## Correções

- Segredos JWT, chave de templates faciais e senha administrativa são passados explicitamente à API pelo full.yml, com obrigatoriedade de valor presente. Senhas bootstrap/migrador não são adicionadas ao ambiente da API.
- Depósito fictício habilitado e documento opcional no perfil local. Biometria real em cadastro/login e DPoP continuam obrigatórios. Esses flags não alteram a regra de produção nem criam integração Pix real.
- install.sh prepara o perfil local por padrão e com --local; só baixa imagens de apresentação com --hub. O painel de apresentação chama o modo --hub explicitamente.
- Arquivos privados são criados com umask 077 e mantidos com modo 0600. O instalador não imprime segredos nem executa conteúdo dos arquivos de configuração.
- Segredos existentes em .env.docker não são trocados. Se os três segredos da API faltarem, são importados do .env antigo. Na primeira criação de .env.docker, os segredos já existentes em .env prevalecem sobre os recém-gerados, preservando chaves de dados anteriores.
- Guia, README e exemplo de configuração atualizados para distinguir os perfis e indicar persistência das chaves.

## Validação operacional

- Stack inteiro novo, com .env vazio e credenciais sintéticas independentes, iniciado em projeto/volume descartáveis sem publicar portas. Frontend, API e PostgreSQL saudáveis; migração concluída.
- O administrador desse stack usa a senha gerada, e a senha padrão de desenvolvimento é recusada.
- Depósito fictício ativo, documento opcional, DPoP obrigatório e biometria sem stub conferidos nas configurações efetivamente carregadas.
- Auditoria runtime e conciliação executadas dentro da API descartável, aprovadas.
- Somente os containers/volume pertencentes ao teste descartável foram removidos.
- Configuração local atual atualizada após backup cifrado. JWT_SECRET, EMBEDDING_KEY e ADMIN_SENHA comparados antes/depois: valores preservados, sem troca de chave facial.
- App, backend e banco do usuário permanecem saudáveis. Chromium real renderizou /login sem erro JavaScript; formulário usa API real e rejeita credenciais fictícias com 401. Login administrativo DPoP 200, consulta autenticada 200 e logout 204.

Os testes desta correção não movimentaram dinheiro nas contas existentes nem leram dados pessoais brutos. A documentação histórica da revisão mantém os achados antes desta correção; este relatório registra a resolução.
