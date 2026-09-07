-- 20260907T1509_camada_esquema: item L5-31-construtor-de-camada-esquema (L5 builder). Idempotente. Sem
-- BEGIN/COMMIT. Aplicada como postgres.
--
-- `plat.camada_campo_meta` guarda o que o PostgreSQL não guarda sobre um campo de camada construído por
-- arrasto: alias (rótulo de tela), domínio (lista de valores codificados, formato compatível com o `domain`
-- de um FeatureServer Esri) e ordem de exibição. Tipo, tamanho, obrigatoriedade e valor padrão continuam
-- só no PostgreSQL (information_schema.columns) — nunca duplicados aqui, para não desalinhar depois de um
-- `ALTER TABLE` feito por outra via. Ganha FK COMPOSTA (tenant_id, item_id) para `plat.item` (nunca só
-- item_id): mesmo que uma policy de RLS falhe silenciosamente em algum caminho futuro, o banco recusa a
-- própria inserção de uma linha de metadado apontando para item de outro inquilino — defesa em profundidade,
-- não o único mecanismo de isolamento (a política abaixo é a linha de frente, igual a toda outra tabela do
-- schema `plat`). Isso exige uma UNIQUE (tenant_id, id) em `plat.item`, que a 011 nunca precisou (a PK já
-- bastava para toda referência simples por id).

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ux_item_tenant_id') THEN
    ALTER TABLE plat.item ADD CONSTRAINT ux_item_tenant_id UNIQUE (tenant_id, id);
  END IF;
END $$;

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
  FOREIGN KEY (tenant_id, item_id) REFERENCES plat.item (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_camada_campo_meta_item ON plat.camada_campo_meta (item_id, ordem);

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
