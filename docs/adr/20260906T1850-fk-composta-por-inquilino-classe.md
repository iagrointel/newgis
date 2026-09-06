# FK composta por inquilino — o resto do schema (item FK-CLASSE-CONSERTO)

## Contexto

O item `L4-01-a-pacote-de-ativos` (turno 3, ramo `wt/stac`, ainda não mesclado a `master`) achou que uma FK
simples (`REFERENCES alvo(id)`) entre duas tabelas que têm `tenant_id` não é filtrada pela RLS: o Postgres
resolve a checagem de referência com o privilégio do DONO da tabela, por baixo de qualquer política. Um
inquilino B, autenticado como `plat_app`, consegue gravar uma linha SUA (`tenant_id = B`) cuja FK aponta
para o `id` de uma linha de OUTRO inquilino (A) — cria dependência cruzada entre inquilinos e vira oráculo
de existência (o uuid de A é aceito, um uuid inventado é recusado; a diferença de resposta entrega
existência sem nunca ler a linha).

A trava escrita para aquele item (`tests/api/test_fk_composta_por_inquilino.py`) varre `pg_constraint` do
schema inteiro, não só as 10 tabelas `plat.rede_*` do item original — achou 55 ocorrências fora da rede,
listadas como exceção nomeada (`PERMITIDAS`) por não serem escopo daquele conserto. 44 delas apontam para
tabelas que já existem em `master`; as outras 11 pertencem a tabelas de trilhas ainda não mescladas.

## Decisão

Mesmo padrão do conserto original, aplicado às 44: cada tabela-alvo ganha `UNIQUE (tenant_id, id)` — trivial,
`id` já é único sozinho, a restrição composta só abre a "porta" para a FK também ser composta — e cada FK
simples vira `FOREIGN KEY (tenant_id, col) REFERENCES alvo (tenant_id, id)`. Com `MATCH SIMPLE` (o padrão), a
composta não é conferida quando algum membro é `NULL` (ex. `item.pasta_id`), preservando a nulidade opcional
de antes.

`ON DELETE` original de cada FK é preservado. Nas 9 que eram `SET NULL` (`item.criado_por/apagado_por/
modificado_por/pasta_id`, `compartilhamento_link.criado_por`, `grupo_membro.convidado_por`,
`papel_personalizado.criado_por`, `provedor_ldap.criado_por/atualizado_por`), a migração usa a sintaxe de
LISTA DE COLUNAS do Postgres 15+ (`ON DELETE SET NULL (col)`) em vez do `ON DELETE SET NULL` liso: sem a
lista, uma FK composta nulifica TODAS as colunas da chave — incluindo `tenant_id`, que é `NOT NULL` em toda
tabela do schema, o que quebraria a exclusão em runtime com uma violação de NOT NULL nunca vista em teste
(só dispara quando a linha referenciada é de fato apagada). Testado em produção rasa: apagar um usuário
referenciado por `papel_personalizado.criado_por` só zera `criado_por`; `tenant_id` da linha filha não muda.

As 11 FKs restantes (tabelas de `exportacao`, `geocodificacao*`, `raster_item`/`raster_colecao`, e
`rede.dono_id`/`rede.importado_por` apontando para `usuario`) não entram como exceção permanente na trava —
ficariam como dívida sem prazo. Quem mesclar a trilha que introduz essas tabelas vai ver a trava acusar a
mesma classe de falha e aplica o mesmo padrão.

## Consequência

`PERMITIDAS` da trava fica vazio: zero FKs simples entre tabelas com `tenant_id` em todo o schema `plat`
(nas tabelas que hoje existem em `master`). A garantia mora no BANCO — qualquer código futuro que grave
numa dessas 44 colunas (rota nova, job, script de manutenção) está protegido pela mesma composta, sem
precisar repetir a checagem de tenant em cada rota.
