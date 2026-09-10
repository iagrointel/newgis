-- L1-07 (mosaico por coleção e pegadas): a linha-espelho em `plat.item` (tipo 'mosaico', ver
-- app/imagens/mosaico.py::registrar) precisa de um `plat.tipo_item` correspondente — sem ele
-- `POST /svc/<token>/stac/mosaicos` cai em `item_tipo_fkey` (409 "em_uso"), o mesmo defeito real que
-- `imagens/mosaico_registrar` sem `plat.evento_tipo` (20260910T2330_mosaico.sql). `familia='raster'`
-- porque o mosaico é derivado de item raster (não há família própria no CHECK de tipo_item, e criar
-- uma para um único tipo não compensa); `tem_dado_fisico=false` porque o mosaico não tem objeto
-- próprio no balde — é sempre uma busca sobre itens que já existem. `modulo_front` reaproveita o
-- módulo de `raster` (mesma família de UI; um módulo dedicado fica para quando a tela "Coleção →
-- Mosaico" for construída, fora deste turno — ver ADR 20260910T2330 §5).
INSERT INTO plat.tipo_item
  (nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona)
VALUES (
  'mosaico', 'raster', 'Mosaico',
  'mosaico de coleção(ões) — busca STAC registrada no pgstac (item L1-07)',
  '{
    "type": "object",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "required": ["colecoes", "hash_pgstac", "criterios"],
    "properties": {
      "colecoes": {"type": "array", "items": {"type": "string"}},
      "hash_pgstac": {"type": "string"},
      "criterios": {"type": "object"}
    },
    "additionalProperties": false
  }'::jsonb,
  1, 'raster', '/static/js/catalogo/tipos/raster.js', '{mapa}', false, 'L1-07'
)
ON CONFLICT (nome) DO NOTHING;
