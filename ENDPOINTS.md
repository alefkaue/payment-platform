# Astro — inventário de endpoints

> Gerado por `backend/scripts/inventario_endpoints.py` a partir das rotas reais (101 rotas).
> Não edite à mão: rode o script de novo quando a API mudar.

- **pública**: sem login (as de autenticação têm limite por IP e/ou DPoP).
- **login + DPoP**: access token (Bearer) + prova DPoP da chave do aparelho + sessão ativa
  (encerrada/expirada cai na hora). Sem login, todas respondem 401/403
  (`tests/test_autorizacao_objetos.py::test_sem_login_nada_protegido_responde`).
- **admin + IP**: além disso, papel admin da plataforma e IP em `ADMIN_IPS_PERMITIDOS`.
- **X-Conta**: opera a conta escolhida; o servidor confere o vínculo ATIVO da pessoa com
  aquela empresa (`deps.conta_atual`). Recurso de outra conta responde 404
  (`tests/test_autorizacao_objetos.py::test_ninguem_usa_recurso_de_outro`).
- Loja/Viagens/Pontos: desligados por padrão (`BENEFICIOS_HABILITADOS=0` → 404).

| Método | Caminho | Autenticação | Conta | Regra adicional no serviço |
|---|---|---|---|---|
| `POST` | `/auth/login` | pública |  | Senha (1º fator) + DPoP; limites por conta+IP, por conta e por IP |
| `POST` | `/auth/login/mfa` | pública |  | Rosto com prova de vida sorteada (2º fator); mesmo aparelho e chave DPoP; atestação opcional (APK) |
| `POST` | `/auth/login/mfa/desafio` | pública |  |  |
| `POST` | `/auth/refresh` | pública |  | Refresh preso à chave DPoP e ao aparelho; rotação; limite por IP |
| `POST` | `/auth/logout` | pública |  | Revoga a sessão inteira (família de refresh) |
| `GET` | `/auth/eu` | login + DPoP |  |  |
| `GET` | `/auth/sessoes` | login + DPoP |  |  |
| `DELETE` | `/auth/sessoes/{sessao_id}` | login + DPoP |  |  |
| `POST` | `/auth/sessoes/encerrar-outras` | login + DPoP |  |  |
| `POST` | `/usuarios` | pública |  | Cadastro com KYC (rosto + documento); limite por IP; resposta neutra |
| `GET` | `/contas` | login + DPoP |  |  |
| `GET` | `/contas/atual` | login + DPoP | X-Conta |  |
| `POST` | `/empresas` | login + DPoP |  | Pessoa com KYC; CNPJ conferido (BrasilAPI) e CPF no quadro de sócios |
| `GET` | `/empresas/atual` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/politica` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/documentos` | login + DPoP | X-Conta |  |
| `POST` | `/empresas/atual/documentos` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/vinculos` | login + DPoP | X-Conta |  |
| `POST` | `/empresas/atual/vinculos` | login + DPoP | X-Conta | PJ: admin; dar poder exige rosto; Grande: 4 olhos |
| `PATCH` | `/empresas/atual/vinculos/{vinculo_id}` | login + DPoP | X-Conta | PJ: admin; aumentar poder/alçada exige rosto; Grande: 4 olhos |
| `POST` | `/empresas/atual/vinculos/{vinculo_id}/suspender` | login + DPoP | X-Conta | PJ: admin; nunca o último admin |
| `POST` | `/empresas/atual/vinculos/{vinculo_id}/reativar` | login + DPoP | X-Conta | PJ: admin; rosto; Grande: 4 olhos |
| `DELETE` | `/empresas/atual/vinculos/{vinculo_id}` | login + DPoP | X-Conta | PJ: admin; nunca o último admin |
| `GET` | `/empresas/atual/pendentes` | login + DPoP | X-Conta | PJ: exceto consulta; expira as vencidas antes de listar |
| `GET` | `/convites` | login + DPoP |  |  |
| `POST` | `/convites/{vinculo_id}/aceitar` | login + DPoP |  | Só a dona do CPF convidado, com KYC e rosto |
| `POST` | `/convites/{vinculo_id}/recusar` | login + DPoP |  |  |
| `GET` | `/empresas/atual/funcionarios` | login + DPoP | X-Conta |  |
| `POST` | `/empresas/atual/funcionarios` | login + DPoP | X-Conta | PJ: admin |
| `DELETE` | `/empresas/atual/funcionarios/{funcionario_id}` | login + DPoP | X-Conta | PJ: admin |
| `POST` | `/empresas/atual/folha/pagar` | login + DPoP | X-Conta | PJ: admin/aprovador/operador; alçada, alçada diária e assinatura conjunta → pendente; destino resolvido pelo CPF no servidor |
| `GET` | `/identidade/kyc` | login + DPoP |  |  |
| `POST` | `/identidade/documentos` | login + DPoP |  |  |
| `POST` | `/biometria/desafios` | pública |  | Desafio de prova de vida (uso único, 120 s) |
| `POST` | `/pagamentos/transferir` | login + DPoP | X-Conta | PJ: admin/aprovador/operador; alçada, alçada diária e assinatura conjunta → pendente; rosto acima de R$ 500; limites e aparelho no lock |
| `POST` | `/pagamentos/lote` | login + DPoP | X-Conta | PJ: admin/aprovador/operador; alçada, alçada diária e assinatura conjunta → pendente (por item); até 100 itens |
| `GET` | `/pagamentos/transacoes` | login + DPoP | X-Conta |  |
| `GET` | `/pagamentos/transacoes/{transacao_id}` | login + DPoP | X-Conta |  |
| `POST` | `/pagamentos/transacoes/{transacao_id}/contestar` | login + DPoP | X-Conta | Só transação da conta em uso (MED) |
| `POST` | `/pagamentos/pendentes/{operacao_id}/decidir` | login + DPoP | X-Conta | Aprovar: admin/aprovador ≠ quem lançou, dentro da alçada, rosto; cancelar: quem lançou |
| `GET` | `/pagamentos/split/simular` | pública |  |  |
| `GET` | `/pagamentos/split/transicao` | pública |  |  |
| `POST` | `/pagamentos/depositar-demo` | login + DPoP | X-Conta | Só com DEPOSITO_DEMO=1 (recusado em produção) |
| `POST` | `/cobrancas` | login + DPoP | X-Conta | PJ: admin/aprovador/operador |
| `GET` | `/cobrancas` | login + DPoP | X-Conta |  |
| `GET` | `/cobrancas/{txid}` | login + DPoP |  | Quem tem o txid; documento do pagador mascarado para terceiros |
| `POST` | `/cobrancas/{txid}/pagar` | login + DPoP | X-Conta | PJ: admin/aprovador/operador; alçada, alçada diária e assinatura conjunta → pendente; pagador indicado na cobrança |
| `POST` | `/cobrancas/{txid}/cancelar` | login + DPoP | X-Conta | PJ que emitiu |
| `POST` | `/cobrancas/{txid}/estornar` | login + DPoP | X-Conta | PJ que emitiu: admin |
| `POST` | `/pix-automatico/autorizacoes` | login + DPoP | X-Conta |  |
| `GET` | `/pix-automatico/autorizacoes` | login + DPoP | X-Conta |  |
| `POST` | `/pix-automatico/autorizacoes/{autorizacao_id}/aceitar` | login + DPoP | X-Conta |  |
| `POST` | `/pix-automatico/autorizacoes/{autorizacao_id}/recusar` | login + DPoP | X-Conta |  |
| `POST` | `/pix-automatico/autorizacoes/{autorizacao_id}/cancelar` | login + DPoP | X-Conta |  |
| `POST` | `/pix-automatico/autorizacoes/{autorizacao_id}/cobrancas` | login + DPoP | X-Conta |  |
| `GET` | `/loja/produtos` | login + DPoP |  |  |
| `GET` | `/loja/produtos/{produto_id}` | login + DPoP |  |  |
| `POST` | `/loja/produtos/{produto_id}/comprar` | login + DPoP | X-Conta |  |
| `GET` | `/viagens/voos` | login + DPoP |  |  |
| `GET` | `/viagens/voos/{voo_id}` | login + DPoP |  |  |
| `POST` | `/viagens/voos/{voo_id}/comprar` | login + DPoP | X-Conta |  |
| `POST` | `/viagens/voos/{voo_id}/resgatar` | login + DPoP | X-Conta |  |
| `GET` | `/pontos` | login + DPoP |  |  |
| `GET` | `/seguranca/limites` | login + DPoP | X-Conta |  |
| `PUT` | `/seguranca/limites` | login + DPoP | X-Conta | PJ: admin; aumento só vale após carência de 24 h |
| `GET` | `/seguranca/dispositivos` | login + DPoP |  |  |
| `GET` | `/seguranca/dispositivos/atual` | login + DPoP |  |  |
| `POST` | `/seguranca/dispositivos/atual/confiar` | login + DPoP |  |  |
| `DELETE` | `/seguranca/dispositivos/{dispositivo_id}` | login + DPoP |  |  |
| `POST` | `/seguranca/dispositivos/{dispositivo_id}/bloquear` | login + DPoP |  |  |
| `POST` | `/seguranca/dispositivos/{dispositivo_id}/desbloquear` | login + DPoP |  | Rosto |
| `GET` | `/seguranca/atividade` | login + DPoP |  |  |
| `GET` | `/empresas/atual/auditoria` | login + DPoP | X-Conta | PJ: admin/aprovador |
| `GET` | `/pix/chaves` | login + DPoP | X-Conta |  |
| `POST` | `/pix/chaves` | login + DPoP | X-Conta |  |
| `DELETE` | `/pix/chaves/{chave_id}` | login + DPoP | X-Conta |  |
| `GET` | `/pix/consultar/{chave}` | login + DPoP |  | Nome mascarado; 60 consultas/hora por pessoa |
| `GET` | `/empresas/atual/tributos` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/creditos` | login + DPoP | X-Conta |  |
| `POST` | `/empresas/atual/creditos` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/webhooks` | login + DPoP | X-Conta |  |
| `POST` | `/empresas/atual/webhooks` | login + DPoP | X-Conta | PJ: admin; URL https pública (anti-SSRF) |
| `DELETE` | `/empresas/atual/webhooks/{webhook_id}` | login + DPoP | X-Conta |  |
| `GET` | `/empresas/atual/webhooks/entregas` | login + DPoP | X-Conta |  |
| `GET` | `/rendimento` | login + DPoP | X-Conta |  |
| `GET` | `/admin/kyc/casos` | admin + IP |  |  |
| `POST` | `/admin/kyc/casos/{caso_id}/decidir` | admin + IP |  |  |
| `POST` | `/admin/depositar` | admin + IP |  | Admin; IP na lista ADMIN_IPS_PERMITIDOS (sem lista: desligado em produção) |
| `GET` | `/admin/contas` | admin + IP |  |  |
| `GET` | `/admin/transacoes` | admin + IP |  |  |
| `POST` | `/admin/transacoes/{transacao_id}/liberar` | admin + IP |  |  |
| `GET` | `/admin/contestacoes` | admin + IP |  |  |
| `POST` | `/admin/contestacoes/{contestacao_id}/decidir` | admin + IP |  |  |
| `GET` | `/admin/tributos/resumo` | admin + IP |  |  |
| `POST` | `/admin/tributos/repassar` | admin + IP |  |  |
| `POST` | `/admin/jobs/liberar-bloqueios` | admin + IP |  |  |
| `POST` | `/admin/jobs/rendimento` | admin + IP |  |  |
| `POST` | `/admin/jobs/recorrencias` | admin + IP |  |  |
| `POST` | `/admin/jobs/webhooks` | admin + IP |  |  |
| `GET` | `/` | pública |  |  |
| `GET` | `/saude` | pública |  |  |
