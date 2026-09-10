-- 20260910T1620_imagens_predefinicao_renderizacao: item L1-02-f-predefinicoes-de-renderizacao-e-legenda.
--
-- As 6 predefinições de FÁBRICA (RGB natural, falsa-cor NIR, NDVI, NDWI, NBR aproximado, relevo por
-- elevação) NÃO moram aqui: são código puro em `app/imagens/predefinicoes.py::FABRICA` (nenhuma tem
-- tenant_id, e uma tabela por inquilino só para replicar o mesmo JSON em toda linha seria o "número
-- digitado" que a casa proíbe). Esta tabela guarda só as predefinições CUSTOM — as que um inquilino
-- monta e nomeia para um item raster seu, no mesmo espírito do `plat.raster_item` (RLS, mesmo padrão
-- de trigger `atualizado_em`).
--
-- `item_id` referencia `plat.item(id)` (o item do CATÁLOGO, tipo 'raster' — o mesmo uuid que aparece em
-- `plat.raster_item.item_id`/pgstac): uma predefinição só existe amarrada a um item existente do mesmo
-- inquilino (FK composta por inquilino — regra travada por tests/api/test_fk_composta_por_inquilino.py
-- desde 20260906T1815 — nunca `id` sozinho, senão o inquilino B consegue amarrar predefinição num item
-- de A pelo oráculo de existência). `plat.item` ainda não tinha `UNIQUE (tenant_id, id)` (só `rede_*`
-- ganhou isso na 20260906T1815); esta migração acrescenta, mesmo padrão idempotente.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'plat' AND t.relname = 'item' AND c.conname = 'item_tenant_id_id_key'
  ) THEN
    ALTER TABLE plat.item ADD CONSTRAINT item_tenant_id_id_key UNIQUE (tenant_id, id);
  END IF;
END $$;
--
-- Só uma predefinição pode ser `padrao` por item (índice único parcial) — é essa que resolve quando o
-- cliente não passa `predef=`/`STYLES=`/`renderingRule` nenhum; trocar o padrão NÃO apaga as antigas
-- (a URL que já embutiu `predef=<nome>&predef_v=<versao>` continua servindo exatamente o que servia).
CREATE TABLE IF NOT EXISTS plat.render_predefinicao (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  item_id            uuid NOT NULL,
  nome               text NOT NULL CHECK (nome ~ '^[a-z0-9][a-z0-9-]{0,58}$'),
  titulo             text NOT NULL CHECK (btrim(titulo) <> '' AND length(titulo) <= 200),
  corpo              jsonb NOT NULL,
  versao             int NOT NULL DEFAULT 1 CHECK (versao >= 1),
  padrao             boolean NOT NULL DEFAULT false,
  criado_por         int,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  atualizado_em      timestamptz NOT NULL DEFAULT now(),
  apagado_em         timestamptz
);
-- nome único por item ENQUANTO viva (apagar e recriar com o mesmo nome é permitido; a versão sobe).
CREATE UNIQUE INDEX IF NOT EXISTS ux_render_predefinicao_nome
  ON plat.render_predefinicao (tenant_id, item_id, nome) WHERE apagado_em IS NULL;
-- só uma predefinição padrão por item (entre as vivas).
CREATE UNIQUE INDEX IF NOT EXISTS ux_render_predefinicao_padrao
  ON plat.render_predefinicao (tenant_id, item_id) WHERE padrao AND apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_render_predefinicao_item
  ON plat.render_predefinicao (tenant_id, item_id) WHERE apagado_em IS NULL;

ALTER TABLE plat.render_predefinicao DROP CONSTRAINT IF EXISTS render_predefinicao_tenant_item_fkey;
ALTER TABLE plat.render_predefinicao ADD CONSTRAINT render_predefinicao_tenant_item_fkey
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE;

CREATE OR REPLACE FUNCTION plat.tg_render_predefinicao_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  IF NEW.corpo IS DISTINCT FROM OLD.corpo THEN
    NEW.versao := OLD.versao + 1;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS render_predefinicao_atualizado_em ON plat.render_predefinicao;
CREATE TRIGGER render_predefinicao_atualizado_em BEFORE UPDATE ON plat.render_predefinicao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_render_predefinicao_atualizado_em();

ALTER TABLE plat.render_predefinicao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_render_predefinicao ON plat.render_predefinicao;
CREATE POLICY p_render_predefinicao ON plat.render_predefinicao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- a 001 já dá SELECT/INSERT/UPDATE/DELETE a plat_app em toda tabela nova do schema (ALTER DEFAULT
-- PRIVILEGES) — GRANT explícito aqui só para a função nova, mesma disciplina de raster_item.sql.
REVOKE ALL ON FUNCTION plat.tg_render_predefinicao_atualizado_em() FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.render_predefinicao TO plat_app;

-- tipos de evento que app/imagens/rotas_predefinicoes.py registra — sem isto a rota dá 500 por
-- evento_tipo_fkey (defeito real medido hoje em L1-02-g/L1-25, corrigido na migração 20260910T0245).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/predefinicao_criar', 'predefinição de renderização criada (L1-02-f)'),
  ('imagens/predefinicao_atualizar', 'predefinição de renderização atualizada (L1-02-f)'),
  ('imagens/predefinicao_apagar', 'predefinição de renderização apagada (L1-02-f)'),
  ('imagens/predefinicao_tornar_padrao', 'predefinição de renderização marcada padrão do item (L1-02-f)')
ON CONFLICT (nome) DO NOTHING;
