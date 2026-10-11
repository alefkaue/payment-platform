## Resultado

Cartão: remover a faixa de informações fictícias do topo.
Status: concluído
Commits: nenhum.
Arquivos alterados: app/src/routes/__root.tsx; este relatório.
Testes: TypeScript aprovado; git diff --check aprovado; aviso ausente no HTML servido em localhost:8081. Sem teste novo para alteração visual simples.
O que NÃO foi feito e por quê: banco, API e regras de simulação não foram alterados; pedido restrito à faixa visual.
Problemas que vi fora do escopo: nenhum novo.
Como testar na mão: abrir http://localhost:8081 e atualizar a página; a faixa não aparece no topo.
