-- 20260908T1911_raster_ciclo_vida: colunas do ciclo de vida do item de imagem (item L1-01-i-ciclo-de-vida-
-- exclusao-e-coleta-de-lixo). `plat.raster_item` já tem `estado` com o valor 'excluido' (migração
-- 20260906T1901); aqui entram as duas colunas que faltavam para a regra da casa:
--   stac        → o corpo STAC do item GUARDADO no momento em que ele sai do pgstac (exclusão lógica); é o
--                 que a restauração dentro da retenção usa para devolver o item ao STAC sem reingestão.
--   excluido_em → quando saiu; junto com `apagado_em` do item do catálogo é o que o relatório de coleta de
--                 lixo usa para separar "na lixeira, dentro da retenção" de "esquecido".
-- E a função de consulta usada pela subrequisição de autorização do nginx (`/_plat_cog_autorizar`), que roda
-- SEM contexto de inquilino (rota pública): SECURITY DEFINER com busca fixa, superfície de uma linha,
-- revogada para PUBLIC — nunca expõe mais que o estado do item pelo par (slug, item_id).
ALTER TABLE plat.raster_item ADD COLUMN IF NOT EXISTS stac jsonb;
ALTER TABLE plat.raster_item ADD COLUMN IF NOT EXISTS excluido_em timestamptz;

CREATE OR REPLACE FUNCTION plat.raster_item_estado_por_item(p_slug text, p_item_id text)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path = plat, pg_temp
AS $$
  SELECT r.estado
  FROM plat.raster_item r
  JOIN plat.tenant t ON t.id = r.tenant_id
  WHERE t.slug = p_slug AND r.item_id = p_item_id
$$;
REVOKE ALL ON FUNCTION plat.raster_item_estado_por_item(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.raster_item_estado_por_item(text, text) TO plat_app;

-- O tipo de item 'raster' ganha a chave `guardar_original` em `dados_item` (o ingestor do L1-01-f aceita
-- manter (true) ou descartar (false, padrão) o arquivo bruto depois de gerar os COGs; o apagamento do bruto
-- reutiliza `imagens.raster_apagar_objetos`). O esquema é additionalProperties:false, sem isto a validação
-- do catálogo recusaria a chave. Idempotente.
UPDATE plat.tipo_item SET esquema = jsonb_set(esquema, '{properties,guardar_original}', '{"type":"boolean"}'::jsonb)
WHERE nome = 'raster' AND NOT (esquema->'properties' ? 'guardar_original');
