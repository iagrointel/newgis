-- Item L0-09-b-editor-iso-mgb: editor de metadado no Perfil MGB 2.0 (INDE), abas essencial/completo, armazenado
-- em jsonb por item. Só a parte NÃO sincronizada com os campos do item (contato, restrições de licença,
-- extensão temporal/espacial declarada, sistema de referência, manutenção, formato de distribuição) vive aqui;
-- título/resumo/palavras-chave/créditos/termos de uso continuam em plat.item (colunas já existentes, migração
-- 011) e são espelhados ao vivo pelo módulo app/catalogo/metadado_mgb.py — nunca duplicados no jsonb, para que
-- "o título É sincronizado" (regra do item) não vire dois lugares de verdade. Idempotente. Sem BEGIN/COMMIT.

ALTER TABLE plat.item ADD COLUMN IF NOT EXISTS metadado_iso jsonb NOT NULL DEFAULT '{}'::jsonb;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'item_metadado_iso_objeto') THEN
    ALTER TABLE plat.item ADD CONSTRAINT item_metadado_iso_objeto CHECK (jsonb_typeof(metadado_iso) = 'object');
  END IF;
END $$;

-- estilo de apresentação do metadado por inquilino (mgb2 padrão; iso19115_3 e dublin_core só mudam rótulo/forma
-- de exibição — o armazenamento em metadado_iso é o mesmo para os três, D do item). Reusa plat.tenant.config
-- (padrão já usado por L0-07-a, migração 034); sem coluna nova.
-- chave: config->>'estilo_metadado' IN ('mgb2','iso19115_3','dublin_core'), padrão 'mgb2' quando ausente.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('itens/metadado_iso_atualizar', 'metadado ISO/MGB do item alterado pelo editor em abas (propriedades.campos)')
ON CONFLICT (nome) DO NOTHING;
