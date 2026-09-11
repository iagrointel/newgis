-- Dois ramos deram vocabulários DIFERENTES para `plat.raster_item.estado`, e a fusão deixou o CHECK de
-- um lado com o código do outro:
--   046_raster_item.sql          → 'registrado', 'ingerindo', 'pronto', 'falhou', 'removido'
--   20260906T1901_raster_item.sql → 'ativo', 'processando', 'erro', 'excluido'
-- O CHECK que venceu foi o primeiro; `app/imagens/raster_item.py` grava o padrão 'ativo' do segundo, e
-- toda ingestão de imagem morria com `violates check constraint "raster_item_estado_check"` DEPOIS de
-- já ter convertido o COG — o trabalho todo perdido no último passo. Medido em 11/09/2026.
--
-- Conserto pela regra da casa para esta classe: UNIÃO dos dois vocabulários, nunca escolher um lado.
-- Escolher um lado quebraria o código do outro, e não há como saber aqui qual dos dois é o "certo";
-- quem quiser reduzir o vocabulário depois tem de mexer nos dois lados juntos, de propósito.
ALTER TABLE plat.raster_item DROP CONSTRAINT IF EXISTS raster_item_estado_check;
ALTER TABLE plat.raster_item ADD CONSTRAINT raster_item_estado_check
  CHECK (estado = ANY (ARRAY[
    'registrado', 'ingerindo', 'pronto', 'falhou', 'removido',
    'ativo', 'processando', 'erro', 'excluido'
  ]));
