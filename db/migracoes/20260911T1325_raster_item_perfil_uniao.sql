-- Mesma classe do `estado`, agora em `plat.raster_item.perfil`. O CHECK que a fusão deixou aceita só
-- perfil único ('visual', 'cientifico', 'referencia'), mas `app/imagens/ingestao.py:268` grava
-- 'visual+cientifico' — que é o que a ingestão de fato produz: os DOIS assets, o visual em JPEG/WebP
-- e o científico em ZSTD, para a mesma imagem. A ingestão morria no último passo, depois de já ter
-- convertido os dois COGs. Medido em 11/09/2026.
--
-- União, não escolha de lado: o valor combinado é legítimo e o código é a fonte da verdade do que a
-- ingestão produz.
ALTER TABLE plat.raster_item DROP CONSTRAINT IF EXISTS raster_item_perfil_check;
ALTER TABLE plat.raster_item ADD CONSTRAINT raster_item_perfil_check
  CHECK (perfil = ANY (ARRAY['visual', 'cientifico', 'referencia', 'visual+cientifico']));
