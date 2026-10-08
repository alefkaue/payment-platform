# Apresentação Astro — slide 10 com o app interativo

Pasta temporária, separada do projeto (`app/`, `site/`, `backend/` não foram tocados). Pode apagar depois da banca.

## O que mudou (2026-10-07)

No slide **10 · A jornada no app**, o carrossel com as 11 telas estáticas foi trocado por **um único celular interativo** (`astro-app.html`, embutido por `<iframe>`). A banca mexe no app dentro da própria apresentação.

- Cada etapa concluída é **salva** (localStorage, chave `astro-demo-v1`) e o app **passa para a próxima tela**.
- A trilha à esquerda mostra as 11 etapas, marca as concluídas e deixa pular para qualquer uma.
- As setas ← → do slide voltam/avançam a etapa.
- No fim, "Recomeçar a jornada" zera tudo.

| # | Etapa | O que dá para fazer | Como avança |
|---|---|---|---|
| 01 | Boas-vindas | — | Abrir conta / Já tenho conta |
| 02 | Login | editar e-mail/CPF | Continuar |
| 03 | Verificação facial | desafio com contagem regressiva (simulado, sem câmera) | Simular movimento |
| 04 | Início PF | cartão, saldo, pontos, atalhos | Pix |
| 05 | Pix | enviar (debita o saldo, sem retenção) ou receber com QR | Trocar para a conta da empresa |
| 06 | Início PJ | retido, repassado, repasse de amanhã | Imposto das suas vendas |
| 07 | Entenda o split | escolher o ano 2026–2033 e simular um valor | Cobrar um cliente |
| 08 | Cobrar com nota | mudar o valor (CBS/IBS recalculam), Pix QR ou boleto | Gerar cobrança |
| 09 | Equipe & alçadas | convidar pessoa | Ver aprovações pendentes |
| 10 | Aprovações pendentes | aprovar / recusar | Ver comprovante |
| 11 | Comprovante | split linha a linha do valor cobrado na etapa 08 | Recomeçar |

## Como abrir

Precisa de servidor local (o iframe não carrega bem via `file://` em alguns navegadores):

```bash
cd apresentacao
python -m http.server 8777
# abrir http://localhost:8777/Astro%20Apresentacao.dc.html
```

## Arquivos

- `Astro Apresentacao.dc.html` — a apresentação (só o slide 10 e os handlers `jPrev`/`jNext` mudaram).
- `astro-app.html` — o app demonstrativo (HTML/JS puro, sem build).
- `support.js`, `image-slot.js`, `site/public/*` — dependências da apresentação.

## Limites (ser honesto com a banca)

- É uma **réplica demonstrativa** das telas, com dados fictícios: não é o build do app React (`app/`) nem fala com o backend.
- A verificação facial é simulada; não liga a câmera.
- As alíquotas seguem o cronograma de `app/src/lib/split.ts` (CBS 8,8% / IBS 17,7% em 2033, estimativas).

## Verificado

- Script do app sem erro de sintaxe; tela 01 conferida por captura no Edge sem janela.
- O runtime da apresentação renderiza o `<iframe>` no slide 10.
- **Não** testado: clique a clique em todas as 11 telas, nem celular/projetor da banca. Passar a jornada inteira uma vez antes de apresentar.

## Próximos passos

1. Percorrer as 11 etapas e ajustar textos/valores.
2. Se sobrar tempo: trocar a réplica pelo build real do app (`npm run build` em `app/`, modo demonstração) dentro do mesmo iframe.
3. Depois da banca, apagar esta pasta/branch.
