-- 20260907T1509_camada_esquema: item L5-31-construtor-de-camada-esquema (L5 builder). Idempotente. Sem
-- BEGIN/COMMIT. Aplicada como postgres.
--
-- `plat.camada_campo_meta` guarda o que o PostgreSQL não guarda sobre um campo de camada construído por
-- arrasto: alias (rótulo de tela), domínio (lista de valores codificados, formato compatível com o `domain`
-- de um FeatureServer Esri) e ordem de exibição. Tipo, tamanho, obrigatoriedade e valor padrão continuam
-- só no PostgreSQL (information_schema.columns) — nunca duplicados aqui, para não desalinhar depois de um
-- `ALTER TABLE` feito por outra via.
--
-- Isolamento por inquilino: a FK é SIMPLES para `plat.item(id)` (a chave primária que já existe; nenhuma
-- constraint única artificial é criada em `plat.item`) e a coerência de inquilino é garantida por GATILHO,
-- exatamente como `plat.item_relacao` e `plat.item_grupo` fazem em 011_catalogo.sql. A linha de frente do
-- isolamento continua sendo a política de RLS abaixo, igual a toda outra tabela do schema `plat`; o gatilho
-- é defesa em profundidade, recusando metadado que aponte para item de outro inquilino.

CREATE TABLE IF NOT EXISTS plat.camada_campo_meta (
  tenant_id  int         NOT NULL REFERENCES plat.tenant(id),
  item_id    uuid        NOT NULL,
  coluna     text        NOT NULL CHECK (coluna ~ '^[a-z][a-z0-9_]{0,62}$'),
  alias      text        CHECK (alias IS NULL OR length(alias) <= 250),
  dominio    jsonb        CHECK (dominio IS NULL OR jsonb_typeof(dominio) = 'array'),
  ordem      int         NOT NULL DEFAULT 0,
  indice     boolean     NOT NULL DEFAULT false,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (item_id, coluna),
  FOREIGN KEY (item_id) REFERENCES plat.item (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_camada_campo_meta_item ON plat.camada_campo_meta (item_id, ordem);

-- coerência de inquilino por gatilho (padrão de plat.item_relacao / plat.item_grupo em 011_catalogo.sql)
CREATE OR REPLACE FUNCTION plat.tg_camada_campo_meta() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = NEW.item_id AND i.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'metadado_de_outro_inquilino';
  END IF;
  IF plat.tenant_atual() IS NOT NULL AND NEW.tenant_id <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'metadado_de_outro_inquilino';
  END IF;
  RETURN NEW;
END $$;
REVOKE EXECUTE ON FUNCTION plat.tg_camada_campo_meta() FROM PUBLIC, plat_app;
DROP TRIGGER IF EXISTS camada_campo_meta_coerente ON plat.camada_campo_meta;
CREATE TRIGGER camada_campo_meta_coerente BEFORE INSERT OR UPDATE ON plat.camada_campo_meta
  FOR EACH ROW EXECUTE FUNCTION plat.tg_camada_campo_meta();

ALTER TABLE plat.camada_campo_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.camada_campo_meta FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_camada_campo_meta ON plat.camada_campo_meta;
CREATE POLICY p_camada_campo_meta ON plat.camada_campo_meta FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.camada_campo_meta TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/criar_esquema', 'camada vazia criada por esquema arrastado (L5-31)'),
  ('camadas/alterar_esquema', 'esquema de camada existente alterado por plano de migração (L5-31)')
ON CONFLICT (nome) DO NOTHING;
