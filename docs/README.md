# Documentação — ASTRO

Índice da documentação. Os documentos **vivos** (referência atual) ficam nas pastas por tema; os
**datados** (relatórios e revisões pontuais) ficam em [`historico/`](historico/).

## 📘 Arquitetura & produto — [`arquitetura/`](arquitetura/)
| Documento | Conteúdo |
|---|---|
| [HANDOFF-V9.md](arquitetura/HANDOFF-V9.md) | Estado do projeto, decisões e próximos passos (handoff atual) |
| [PLANO.md](arquitetura/PLANO.md) | Plano de produto |
| [ENDPOINTS.md](arquitetura/ENDPOINTS.md) | Superfície da API |
| [BANCO.md](arquitetura/BANCO.md) | Estrutura e operação do banco de dados |
| [CADASTRO.md](arquitetura/CADASTRO.md) | Regras de cadastro/identidade |
| [PERIMETRO-API.md](arquitetura/PERIMETRO-API.md) | Perímetro e regras de borda da API |
| [ACESSO_E_REGRAS_FINANCEIRAS.md](arquitetura/ACESSO_E_REGRAS_FINANCEIRAS.md) | Acesso PF/PJ e regras financeiras |

## 🔒 Segurança — [`seguranca/`](seguranca/)
| Documento | Conteúdo |
|---|---|
| [SECURITY.md](seguranca/SECURITY.md) | Índice de segurança |
| [SEGURANCA.md](seguranca/SEGURANCA.md) | Controles de segurança (detalhado) |
| [SECURITY_AUDIT.md](seguranca/SECURITY_AUDIT.md) | Achados de auditoria e correções |
| [THREAT_MODEL.md](seguranca/THREAT_MODEL.md) | Modelagem de ameaças |
| [PENTEST.md](seguranca/PENTEST.md) | Regras e escopo do pentest |

## ⚙️ Operação / deploy — [`operacao/`](operacao/)
| Documento | Conteúdo |
|---|---|
| [AZURE.md](operacao/AZURE.md) | Deploy na Azure (Container Apps + ACR + Key Vault) |
| [AZURE-STUDENTS-TESTE.md](operacao/AZURE-STUDENTS-TESTE.md) | Aplicação publicada: acesso, segurança, custos, pausa e prioridades |
| [DOCUMENTO-COLETA-ACADEMICA.md](operacao/DOCUMENTO-COLETA-ACADEMICA.md) | Coleta documental sem validar identidade/rosto no modo acadêmico; alteração apenas no GitHub |
| [AZURE-IMPLANTACAO-ACADEMICA.md](operacao/AZURE-IMPLANTACAO-ACADEMICA.md) | Sequência atual conforme os três diagramas, orçamento e migrador separado |
| [RODAR-NO-PC.md](operacao/RODAR-NO-PC.md) | Rodar no PC / emulador Android |
| [COMO-RODAR-REMOTO.md](operacao/COMO-RODAR-REMOTO.md) | Subir por túneis HTTPS (ambiente de pentest) |
| [HANDOFF-DEPLOY-TOTP-AZURE.md](operacao/HANDOFF-DEPLOY-TOTP-AZURE.md) | Deploy da autenticação por senha/TOTP no Azure |
| [HANDOFF-FRONTEND-SENHA-TOTP.md](operacao/HANDOFF-FRONTEND-SENHA-TOTP.md) | Handoff do frontend de confirmação por senha/TOTP |
| [PAGAMENTO-SENHA-TOTP-E-ATIVACAO-IMEDIATA.md](operacao/PAGAMENTO-SENHA-TOTP-E-ATIVACAO-IMEDIATA.md) | Relatório de autenticação e ativação imediata |

## 🤖 Colaboração com IAs — [`ia/`](ia/)
Notas de trabalho com assistentes (GPT, Gemini).

## 🔎 Auditoria — [`auditoria-personas/`](auditoria-personas/)
Conselho de 15 subagentes + relatórios `00`–`11` (inventário, rotas, avaliação técnica, jornadas,
achados, roadmap, casos de teste, regulatório, limitações). Começe por
[01-RESUMO-EXECUTIVO.md](auditoria-personas/01-RESUMO-EXECUTIVO.md).

## 🗂️ Histórico — [`historico/`](historico/)
Relatórios e revisões datados (snapshots), incluindo o HANDOFF antigo. Mantidos como registro; para a
referência atual, use as pastas por tema acima.

- [Análise crítica da arquitetura Azure — 12/10/2026](historico/ANALISE-CRITICA-AZURE-2026-10-12.md): evidências do código, pontos positivos, prioridades P0/P1/P2 e validações pendentes.
- [Revisão de problemas R01–R10 — 14/10/2026](historico/REVISAO-PROBLEMAS-2026-10-14.md): achados de lógica financeira, idempotência, alçadas e correções aplicadas.
- [Melhorias de cadastro e facial — 15/10/2026](historico/MELHORIAS-CADASTRO-2026-10-15.md): data de nascimento, rosto do documento, calibração do piscar.
- [Requisitos de lógica e front — referência](historico/MELHORIAS-LOGICA-FRONT.md): checklist de coerência PF/PJ usado como base durante o desenvolvimento.
- [Prompt de correção R01–R10](historico/PROMPT-CORRECAO-R01-R10.md): instrução usada para corrigir os achados da revisão de 14/10.
