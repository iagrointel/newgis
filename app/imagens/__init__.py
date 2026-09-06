"""Catálogo de imagens (item L1-01-a): o pgstac (schema `pgstac`, global ao banco, instalado por
`pypgstac migrate`/`db/pgstac_instalar.sh`) guarda o STAC; o isolamento por inquilino, que o pgstac não
tem, vem de fora dele — nome de coleção `<tenant_id>-<slug>` (app/imagens/pgstac.py) e da tabela-espelho
`plat.raster_item`, com RLS de verdade (app/imagens/raster_item.py). A API fica em app/imagens/rotas_stac.py,
montada em `/svc/<token>/stac/`."""
