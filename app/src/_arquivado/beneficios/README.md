# Benefícios PF arquivados (Loja, Viagens e pontos)

Tirados do app em 09/10/2026 a pedido do Alef: o foco agora é segurança, e cada tela/endpoint a mais é
superfície de ataque no pentest (ver `SEGURANCA.md`, item 6). **Nada foi apagado.**

## O que está aqui
- `_app.loja.tsx`, `_app.loja.$id.tsx` — Loja (compra em reais, pontos, verificação facial acima de R$ 500).
- `_app.viagens.tsx` — Viagens (compra em reais e resgate de passagem com pontos).

Esta pasta está fora de `src/routes`, então o roteador não cria as páginas; também está fora do `tsc`
(`tsconfig.json` → `exclude`) e do `eslint`.

## O que continua no código (sem uso)
- `src/lib/api.ts`: `listarProdutos`, `produtoPorId`, `comprarProduto`, `buscarVoos`, `vooPorId`,
  `comprarPassagem`, `resgatarPassagem`, `pontosDaCompra`.
- `src/components/payflow/ui.tsx`: `ProdutoCard`, `VooCard`.
- Backend: `routers/beneficios.py` e `services/beneficios_service.py`, **desligados por padrão**
  (`BENEFICIOS_HABILITADOS=0` → as rotas respondem 404 e o catálogo não é criado no boot).

## Para reativar
1. `git mv src/_arquivado/beneficios/_app.*.tsx src/routes/` (o `routeTree.gen.ts` se refaz no `npm run dev`).
2. Devolver os atalhos: `src/lib/nav.ts` (Loja na barra PF, Viagens no "Mais"), banners e atalhos em
   `src/routes/_app.inicio.tsx`, botão "Usar meus pontos" em `_app.cartoes.tsx`, e a leitura de `/pontos` em
   `minhaConta()` (`src/lib/api.ts`).
3. No backend, `BENEFICIOS_HABILITADOS=1`.
