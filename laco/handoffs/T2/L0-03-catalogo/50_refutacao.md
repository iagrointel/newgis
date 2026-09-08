# Refutação — L0-03-catalogo (adversário, T2)

**Veredito: PASSA.** Cinco ataques essenciais rodados ao vivo contra https://plat.iagrointel.com (sessões
`demo`/`demo2`), nenhum passou.

1. **Link**: criar → acesso anônimo 200 → revogar (204) → acesso anônimo 404 `link_invalido` em 30 ms;
   20 pedidos simultâneos pós-revogação = 20×404, 0×200.
2. **Link anônimo não entrega identidade**: `dono` vem só `{"id":1}`, sem login/nome; `criado_por`/
   `modificado_por`/`apagado_por` vêm `null`. Confirma o conserto do commit `a591581` (antes vazava
   "Administrador demo" + login de quem criou/alterou).
3. **Cruzado A→B**: 23 chamadas (sessão de `demo` contra item/pasta/versão de `demo2`) cobrindo GET/PUT/
   PATCH/DELETE/POST em item, compartilhamento, versões, publicar, restaurar, miniatura, links, usado-por,
   criado-a-partir-de, ordem-de-exclusão, mover, relações, favoritos, lote, transferir, pastas — 0×200,
   todas 404 (a RLS não distingue "existe mas não posso" de "não existe").
4. **Apagar protegido / com dependente**: item protegido → DELETE 409 `item_protegido`; item usado por
   3 (2 `vista_de_camada` + 1 `mapa`) → DELETE 409 `possui_dependentes` com a árvore completa; `POST
   /api/itens/lote` com a mesma ação devolve `recusados`, não `feitos`. Item confirmado intacto depois.
5. **Forjar UPDATE de versão imutável como `plat_app`**: grants reais mostram só `SELECT` em
   `plat.item_versao`; UPDATE/INSERT/DELETE diretos via `psql` como `plat_app` → `permission denied for
   table item_versao` nos três casos.

Nada a corrigir nesta rodada. Serviços (`plat-api`, `plat-worker`) seguem ativos; itens de teste criados
pelo adversário foram apagados ao final.
