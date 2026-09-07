"""Edição transacional de feições (item L2-03-a-api-edicao-transacional): `POST /api/camadas/{id}/edicoes` é a
ÚNICA porta de escrita de feição para navegador, PWA, FeatureServer (L2-04-d) e OGC (L2-04-g) — o equivalente do
`applyEdits` da Esri. Reaproveita a tabela de camada que `app/ingestao/carregar.py` já cria (`plat.camada_preparar`,
029_ingestao_vetor.sql: FORCE RLS por `tenant_id`, coluna `versao` para concorrência otimista, `criado_por`/
`atualizado_por`/`criado_em`/`atualizado_em` de rastreio) — nenhuma tabela nova nesta trilha."""
