-- A união dos ramos deixou `plat.raster_item` com a chave primária `(colecao, item_id)`, enquanto
-- `app/imagens/raster_item.py` grava com `ON CONFLICT (tenant_id, colecao, item_id)`. O Postgres
-- exige que a lista do ON CONFLICT case EXATAMENTE com uma restrição única, e recusa com
-- `there is no unique or exclusion constraint matching the ON CONFLICT specification`.
-- Efeito medido em 11/09/2026: toda ingestão de imagem falhava depois de já ter convertido o COG.
--
-- Dois ramos desenharam a tabela de formas diferentes (046_raster_item.sql com a coleção como chave,
-- 20260906T1901_raster_item.sql com `id` sintético mais `tenant_id`), e a que se aplicou primeiro
-- venceu. Não se troca a chave primária aqui: a coluna `colecao` já carrega o inquilino no nome, com
-- CHECK que obriga `colecao = tenant_id || '-' || slug`, então `(colecao, item_id)` já é único por
-- inquilino. O que falta é só a restrição na FORMA que o código pede.
ALTER TABLE plat.raster_item
  DROP CONSTRAINT IF EXISTS uq_raster_item_tenant_colecao_item,
  ADD CONSTRAINT uq_raster_item_tenant_colecao_item UNIQUE (tenant_id, colecao, item_id);
