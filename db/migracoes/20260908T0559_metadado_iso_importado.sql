-- Item L0-09-c-xml-iso-validacao: importação de metadado ISO 19139 para dentro do item. O que a ISO traz e não
-- tem coluna própria (contato, sistema de referência, formato de distribuição, extensão declarada) é gravado em
-- `plat.item.metadado_iso`, a MESMA coluna e a MESMA forma que o item irmão L0-09-b desenhou para o editor MGB.
-- A instrução é idêntica e idempotente de propósito: se o ramo do L0-09-b entrar antes, esta migração não faz
-- nada; se entrar depois, a dele não faz nada. Coluna única, sem segundo armazém de metadado.
-- Sem BEGIN/COMMIT (o aplicador embrulha).

ALTER TABLE plat.item ADD COLUMN IF NOT EXISTS metadado_iso jsonb NOT NULL DEFAULT '{}'::jsonb;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'item_metadado_iso_objeto') THEN
    ALTER TABLE plat.item ADD CONSTRAINT item_metadado_iso_objeto CHECK (jsonb_typeof(metadado_iso) = 'object');
  END IF;
END $$;
