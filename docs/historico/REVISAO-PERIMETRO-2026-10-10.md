## Resultado

Cartão: reforçar a proteção do app/API e criar rotas de isca.

Status: concluído no ambiente local; infraestrutura Azure ainda não publicada.

Commits: nenhum commit ou push novo nesta tarefa.

Arquivos alterados nesta etapa:

- backend/app/core/perimetro.py: iscas, limites de tráfego, tamanho real, tempo
  e memória de corpos, métodos e validação de Host antes de receber uploads.
- backend/app/core/config.py e .env.example: configurações do perímetro.
- backend/app/main.py e backend/app/core/logs.py: integração e erros sem
  mensagem/traceback com possível segredo; logs HTTP de bibliotecas restringidos.
- backend/entrypoint.sh: concorrência, backlog e keep-alive limitados no servidor.
- backend/tests/test_perimetro.py, test_seguranca_api.py e conftest.py:
  regressões e isolamento do orçamento de tráfego por teste.
- docs/PERIMETRO-API.md e este relatório: operação, iscas e limites.

As alterações de banco da tarefa anterior foram preservadas. O inventário de
endpoints foi regenerado sem alteração: 109 rotas reais; as sete iscas ficam no
middleware e fora do OpenAPI.

Testes:

- Backend completo: 514 passaram / 43 pulados, com um aviso de depreciação do
  TestClient. Após os ajustes finais de logs/Host, a suíte específica passou com
  53 testes, incluindo uma regressão nova para traceback sem segredo.
- PostgreSQL restrito: 28 testes aprovados; migração upgrade/downgrade/upgrade
  e Alembic check aprovados. Nenhum modelo foi alterado.
- Compilação Python, sintaxe do entrypoint e git diff --check aprovados.
- API /pronto respondeu 200, isca respondeu 404 e Host forjado respondeu 400;
  app respondeu 200. Ambiente local reiniciado com os controles novos.
- App não foi alterado; testes/TypeScript da etapa anterior continuam como
  referência (218 passaram / 2 pulados, TypeScript e build aprovados).

O que NÃO foi feito e por quê: deploy, WAF, alertas externos e bloqueio da origem
dependem do provisionamento Azure, fora desta execução local. Iscas não entregam
credenciais/arquivos falsos nem bloqueiam permanentemente redes compartilhadas.
O balde é por processo, limitado em memória; não impede sozinho ataques distribuídos
ou volumétricos. Não há garantia de invulnerabilidade.

Problemas que vi fora do escopo: configurações de demonstração e a comparação
documento/selfie informativa descritas no relatório anterior continuam exigindo
revisão antes de produção. Ativar HTTP_HOSTS, redes de proxy confiável e proteção
compartilhada na borda para os domínios finais. Logs antigos permanecem restritos
fora do Git e precisam de política de retenção.

Como testar na mão:

1. Abrir http://localhost:8081 e usar os fluxos existentes.
2. Conferir http://localhost:8765/pronto.
3. Abrir http://localhost:8765/.env: deve receber 404 sem arquivo ou segredo.
4. Buscar sondagem_rota_isca no log local da API: contém apenas identificador
   temporário de origem e nome da isca, sem corpo ou query string.
5. Consultar docs/PERIMETRO-API.md para configuração e limitações no deploy.
