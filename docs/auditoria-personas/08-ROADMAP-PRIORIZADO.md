# 08 — Roadmap priorizado

> Baseado nos achados **verificados** (06) + lacunas de auditoria. Esforço em P(equeno)/M(édio)/G(rande).
> Sem datas. Como nenhum P0/P1 foi confirmado nas áreas revisadas, S0 é **confirmação**, não correção urgente.

## S0 — Fechar a confiança de segurança/finanças (confirmar, não corrigir)
| # | Tarefa | Competência | Dependência | Teste de aceite | Esforço |
|---|---|---|---|---|---|
| S0-1 | Varrer TODAS as rotas por id (`{id}`/`{txid}`/`{vinculo_id}`) e escrita PJ e garantir teste negativo de autorização/IDOR | segurança + QA | matriz de rotas (00) | suíte falha se uma rota aceitar acesso de outra conta/papel | M |
| S0-2 | Reexecutar as 4 análises independentes da Onda 1 (caíram no 429) e o auditor cético | coordenador | limite de uso | 4 relatórios + reclassificação | M |
| S0-3 | Teste adversarial de liveness/anti-spoof (foto/vídeo/máscara) e revisão de retenção de template (LGPD) | segurança + regulatório | ambiente com câmera | relatório de eficácia com cenários | G |

## S1 — Fechar fluxos principais PF/PJ (depende das jornadas, pendentes)
| # | Tarefa | Competência | Teste de aceite | Esforço |
|---|---|---|---|---|
| S1-1 | Percorrer J01–J14 (Fase 2) e registrar o passo exato de atrito por perfil | UX + personas | 14 percursos com resultado observado | G |
| S1-2 | Confirmar paridade de regras mock×backend (evitar demo enganosa) | arquitetura + QA | divergências listadas com arquivo:linha | M |
| S1-3 | Garantir caminho claro quando biometria/câmera falha (alternativa segura) | UX + segurança | fluxo documentado e testado | M |

## S2 — Arquitetura de informação, desktop e acessibilidade (pendentes)
| # | Tarefa | Competência | Teste de aceite | Esforço |
|---|---|---|---|---|
| S2-1 | Avaliar largura fixa de telefone no desktop para tesouraria PJ; propor layout desktop | UX/UI | wireframe + justificativa | M |
| S2-2 | Auditoria WCAG 2.2 AA (teclado, foco, contraste, leitor de tela) | QA/acessibilidade | checklist AA por tela crítica | G |
| S2-3 | Documentar o padrão "gate de papel no service" (ASTRO-001) | arquitetura | doc + teste guardião | P |

## S3 — Evolução de produto (depois do regulatório, pendente)
| # | Tarefa | Competência | Teste de aceite | Esforço |
|---|---|---|---|---|
| S3-1 | Revisar promessas do site/app vs. protótipo (banco/Pix/FGC/rendimento/split-2026) | regulatório | cada alegação com texto corrigido + fonte datada | M |
| S3-2 | Transparência de simulação em comprovantes/extratos | UX + regulatório | rótulo "simulação" visível nos artefatos | P |

## Observação
S1–S3 dependem das ondas de análise **ainda não executadas**. Priorizar S0-1 e S0-2 porque consolidam o
que já está forte e fecham a cobertura de autorização — o ponto mais sensível para o pentest dos outros grupos.
