-- L1-07 (mosaico por coleção e pegadas): `plat.mosaico` é a tabela-espelho de uma busca STAC
-- REGISTRADA no pgstac (`pgstac.search_query()` — a mesma função SQL que o `POST /searches/register`
-- do titiler-pgstac chama por baixo; ver docs/adr/20260910T2330-mosaico-busca-registrada.md). O
-- pgstac guarda a busca (schema `pgstac.searches`, PK = hash, SEM isolamento por inquilino); quem
-- autoriza "este inquilino pode ver este mosaico" é sempre esta tabela — mesmo padrão de
-- 20260906T1901_raster_item.sql.
--
-- O id exposto ao cliente (`plat.mosaico.id`) é um uuid PRÓPRIO, não o hash md5 do pgstac: o hash não
-- bate no formato exigido por `app/auth/escopos.py` (`tiles:ler:<uuid>`) para escopo de token por
-- item, e a validação de escopo (`item_legivel`) exige uma linha em `plat.item` — por isso todo
-- mosaico registrado também vira uma linha em `plat.item` (tipo 'mosaico'), com o MESMO id.
-- Idempotência ("a mesma busca registrada duas vezes devolve o mesmo id", cláusula do portão) vem do
-- UNIQUE(tenant_id, hash): a segunda chamada bate no ON CONFLICT e devolve a linha existente.
CREATE TABLE IF NOT EXISTS plat.mosaico (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  hash           text NOT NULL CHECK (hash ~ '^[0-9a-f]{32}$'),
  nome           text NOT NULL CHECK (length(nome) BETWEEN 1 AND 250),
  colecoes       text[] NOT NULL CHECK (cardinality(colecoes) BETWEEN 1 AND 20),
  criterios      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(criterios) = 'object'),
  busca          jsonb NOT NULL CHECK (jsonb_typeof(busca) = 'object'),  -- payload completo enviado a pgstac.search_query (auditoria/replay)
  estado         text NOT NULL DEFAULT 'ativo' CHECK (estado IN ('ativo', 'removido')),
  criado_por     int,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, hash)
);
CREATE INDEX IF NOT EXISTS ix_mosaico_tenant ON plat.mosaico (tenant_id);

CREATE OR REPLACE FUNCTION plat.tg_mosaico_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS mosaico_atualizado_em ON plat.mosaico;
CREATE TRIGGER mosaico_atualizado_em BEFORE UPDATE ON plat.mosaico
  FOR EACH ROW EXECUTE FUNCTION plat.tg_mosaico_atualizado_em();

ALTER TABLE plat.mosaico ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_mosaico ON plat.mosaico;
CREATE POLICY p_mosaico ON plat.mosaico FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

REVOKE ALL ON FUNCTION plat.tg_mosaico_atualizado_em() FROM PUBLIC;

-- rotas novas (registrar/remover mosaico) registram evento; sem isto o INSERT em plat.evento cai em
-- evento_tipo_fkey (500) — o mesmo defeito documentado em 20260910T0245_imagens_evento_tipo.sql.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/mosaico_registrar', 'mosaico (L1-07): busca STAC registrada no pgstac'),
  ('imagens/mosaico_remover', 'mosaico (L1-07): remoção do registro (a busca em pgstac.searches fica, é inerte sem a linha aqui)')
ON CONFLICT (nome) DO NOTHING;
