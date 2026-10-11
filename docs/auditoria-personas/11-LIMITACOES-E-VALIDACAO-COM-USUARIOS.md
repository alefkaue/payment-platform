# 11 — Limitações e validação com usuários

## O que NÃO foi possível inspecionar nesta rodada
- **Ondas de subagentes** (técnica 1 completa, técnica 2, produto, clientes): os 4 agentes da Onda 1
  foram lançados mas **falharam por limite de uso da sessão (HTTP 429)** antes de produzir relatório. As
  demais ondas não chegaram a rodar. Os 15 arquivos de agente existem e podem ser reinvocados.
- **Jornadas J01–J14 (Fase 2):** não percorridas com front/back no ar. Qualquer afirmação de jornada aqui
  seria inspeção de fluxo por código, não teste executado.
- **Testes:** 448 funções no backend e 43 no front foram **contadas**, não **executadas** nesta rodada.
- **Biometria/liveness:** eficácia anti-spoof exige teste adversarial com câmera — não realizado.
- **Regulatório/promessas, UX, acessibilidade (WCAG), SRE/CI/backup:** não auditados.

## Conclusões que dependem de ambiente
- Concorrência real (duas transferências simultâneas, replay) foi lida no código (lock + idempotência),
  mas **não reproduzida** em execução — marcar como "forte hipótese" até rodar o teste.
- Paridade mock×backend depende de comparar execução dos dois modos.
- Políticas de segurança diferentes entre teste e produção dependem de inspecionar o deploy real.

## O que foi de fato verificado (para calibrar confiança)
Autorização (`deps.py`), fluxo financeiro (`pagamento_service.py`), gate de papel
(`equipe/folha/cobranca_service.py`) e amostra de IDOR (`cobrancas.py`) — lidos no commit `289effb`. Ver
`06-MATRIZ-DE-ACHADOS.md`.

## Protocolo para validação com usuários reais (personas de IA NÃO substituem)
As personas (`astro-pf-*`, `astro-mei-*`, `astro-pme-*`, `astro-grande-*`) simulam **tarefas**, não
opiniões reais. Para validar de verdade:
1. Recrutar **3–5 pessoas PF** (variando idade e familiaridade financeira) e **3–5 PJ/operadores** (MEI,
   PME, alguém de tesouraria).
2. Tarefas sem ajuda: PF — cadastrar, entrar com rosto, enviar Pix, achar comprovante, entender o que é
   simulado. PJ — convidar operador por CPF, configurar alçada, emitir cobrança, aprovar pendência.
3. Medir: taxa de conclusão, passo onde travou, erros, tempo, e frases ditas (sem induzir).
4. Registrar separadamente **fato observado** × **hipótese** × **preferência**.
5. Priorizar correções pelo impacto na conclusão da tarefa, não por gosto.

## Nota de integridade
Este material foi mantido conservador de propósito: só afirma o que foi lido no código, marca o resto como
pendente e não converte "não verificado" em nota nem em aprovação. O objetivo não é elogiar nem condenar o
ASTRO — é apontar, com evidência, o que foi confirmado e o que ainda precisa ser testado.
