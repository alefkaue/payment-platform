# Perímetro HTTP e rotas de isca

A proteção principal continua sendo autenticação, DPoP, autorização por usuário e
conta, limites financeiros, consultas parametrizadas e papel restrito no PostgreSQL.
Iscas ajudam a detectar sondagens; não escondem as rotas reais de quem inspeciona o app.

Antes de acessar o banco, a API aplica:

- Balde por IP com capacidade HTTP_REQUISICOES_MINUTO (padrão 600), recarga
  proporcional por minuto e resposta 429. Cabeçalhos de IP só são aceitos dos
  proxies configurados como confiáveis. Limites específicos de login continuam.
- Memória limitada a 10.000 origens por processo, com descarte das mais antigas.
  Rotacionar muitos IPs pode contornar esse limite; ele não substitui um WAF.
- Corpo limitado a 48 MiB pelos bytes recebidos, inclusive com Content-Length
  falso ou envio fragmentado. Tamanhos inválidos/duplicados são recusados.
  A leitura tem prazo total de 30 segundos.
- Orçamento de 96 MiB de corpos em trânsito por processo; excesso recebe 503.
  A reserva é liberada ao terminar ou desconectar. Cópias transitórias, imagens
  decodificadas e outras estruturas também consomem memória; limitar o container.
- Métodos permitidos: GET, HEAD, POST, PUT, PATCH, DELETE e OPTIONS.
- Validação opcional de Host por HTTP_HOSTS (lista separada por vírgulas, sem
  esquema/porta). Preencher com os hosts da API e sondas no deploy.

GET/HEAD em /saude e /pronto não consomem o balde geral para preservar sondas.
A borda deve limitar também esses endpoints; prontidão ainda consulta o banco.

## Iscas

Endereços interceptados antes do banco, sem executar ações ou devolver segredos:

`/.env`, `/.git/config`, `/wp-login.php`, `/phpmyadmin`, `/admin/backup.sql`,
`/api/debug`, `/backup/database.sql`.

Respondem 404, não aparecem no OpenAPI e não interceptam endpoints administrativos
reais. O evento sondagem_rota_isca registra somente o identificador da isca e um
HMAC temporário da origem, sem IP bruto, query string, corpo ou Authorization.
Registra no máximo um evento por origem/minuto dentro do conjunto limitado de
origens. A chave muda ao reiniciar o processo.

Uma visita não bloqueia permanentemente um IP: usuários e atacantes podem compartilhar
NAT. Excesso de tráfego recebe o limite temporário geral. Não há credenciais falsas,
painel falso ou atraso artificial que consuma recursos.

## Produção e Azure

Não houve deploy nesta revisão. Configurar HTTPS, hosts permitidos, proxy confiável,
WAF/Front Door com limites compartilhados, restrição do acesso direto à origem e
alertas de sondagem. O balde em memória reinicia com o processo e não é compartilhado
entre workers/réplicas. Conexões e envio lento precisam de limites também na borda.
O identificador público de Front Door sozinho não torna um remetente confiável.

O servidor de produção limita concorrência a 64 conexões/tarefas, fila de conexões
a 128 e keep-alive a 5 segundos. Dimensionar workers e réplicas junto ao pool do
banco; a borda continua responsável por ataques volumétricos.

Erros inesperados registram request-id e tipo, sem mensagem/traceback que possam
carregar credenciais. Swagger é desligado por padrão em produção; isso não substitui
autorização. Não habilitar logs de corpo, tokens ou dados de clientes.

Referências: [middleware Starlette](https://www.starlette.io/middleware/) e
[segurança REST OWASP](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).


## Correções do pentest local

Cabeçalhos Host, Authorization, DPoP, X-Conta, X-Dispositivo-Id e Idempotency-Key
não podem ser duplicados. A ambiguidade é recusada antes dos serviços.

DPoP confere a URI completa da API (origem e caminho), além do método, horário,
assinatura e replay. DPOP_ORIGEM_PUBLICA é obrigatória com HTTPS em produção e
precisa coincidir com a URL usada pelo app; no ambiente local foi configurada como
http://127.0.0.1:8765. Não usa X-Forwarded-Host fornecido pelo cliente. O Bicep passa
a origem do Front Door; prefixos reescritos pelo proxy precisam de configuração
compatível antes de publicar. O logout também exige a chave da sessão quando o
refresh token é vinculado a DPoP.

Imagens JPEG/PNG/WEBP têm seus cabeçalhos inspecionados antes da alocação de pixels
no OpenCV: até 6.000 por lado e 12 milhões de pixels. Sequências faciais são
reduzidas a até 1.280 no maior lado antes de acumular quadros. A análise PDF percorre
a estrutura de objetos, inclusive nomes escapados, com limite de complexidade;
recusa scripts, ações automáticas e anexos. Esses controles não substituem limites
do container nem atualizações das bibliotecas.

Em produção, comparação facial divergente reprova KYC; ausência ou dúvida impede
aprovação automática e segue para análise. Desenvolvimento mantém o modo
informativo de demonstração. A representação societária exige nome e documento
compatíveis; sem evidência suficiente, produção não atribui acesso à empresa.
