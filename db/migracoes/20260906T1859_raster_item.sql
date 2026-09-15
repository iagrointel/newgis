-- 046_raster_item: espelho de autorização do catálogo de imagens (item L1-01-a-pgstac-e-stac-api-por-inquilino;
-- ADR 0011). O STAC em si vive no schema `pgstac` (instalado por `pypgstac migrate` no passo db/migrar_pgstac.sh,
-- chamado por db/migrar.sh DEPOIS das migrações SQL — por isso este arquivo não cita role nem função do pgstac).
-- O pgstac não tem RLS nem noção de inquilino: quem diz "esta coleção/este item é deste inquilino e está neste
-- estado" são as duas tabelas abaixo, com RLS igual ao resto do schema plat. Regra dupla (L1_CONCEITO C1/C16):
-- (1) toda coleção do pgstac chama-se '<tenant_id>-<slug>' (CHECK aqui); (2) toda leitura/escrita do pgstac passa
-- pela API da casa, que restringe `collections` à lista deste espelho. Idempotente. Sem BEGIN/COMMIT.

-- versão do pgstac aplicada (o nome NÃO entra em plat.versao_migracao: aquela tabela reflete só db/migracoes/*.sql)
CREATE TABLE IF NOT EXISTS plat.versao_pgstac (
  versao        text PRIMARY KEY,           -- pgstac.get_version() depois do migrate (ex. '0.9.12')
  pypgstac      text NOT NULL,              -- versão do pacote pypgstac da venv que aplicou
  aplicada_em   timestamptz NOT NULL DEFAULT now(),
  aplicada_por  text NOT NULL DEFAULT current_user
);

CREATE TABLE IF NOT EXISTS plat.raster_colecao (
  colecao     text PRIMARY KEY,             -- id da coleção no pgstac: '<tenant_id>-<slug>'
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  slug        text NOT NULL,
  titulo      text,
  criado_por  int REFERENCES plat.usuario(id),
  criado_em   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_raster_colecao_slug    CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  CONSTRAINT ck_raster_colecao_prefixo CHECK (colecao = tenant_id::text || '-' || slug),
  CONSTRAINT uq_raster_colecao_slug    UNIQUE (tenant_id, slug)
);
CREATE INDEX IF NOT EXISTS ix_raster_colecao_tenant ON plat.raster_colecao (tenant_id);

CREATE TABLE IF NOT EXISTS plat.raster_item (
  colecao        text NOT NULL REFERENCES plat.raster_colecao(colecao) ON DELETE CASCADE,
  item_id        text NOT NULL,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  sha256         text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  perfil         text NOT NULL DEFAULT 'visual' CHECK (perfil IN ('visual', 'cientifico', 'referencia')),
  bytes          bigint NOT NULL DEFAULT 0 CHECK (bytes >= 0),
  estado         text NOT NULL DEFAULT 'registrado'
                 CHECK (estado IN ('registrado', 'ingerindo', 'pronto', 'falhou', 'removido')),
  origem         text NOT NULL DEFAULT 'referenciado' CHECK (origem IN ('copiado', 'referenciado')),
  licenca        text,
  criado_por     int REFERENCES plat.usuario(id),
  criado_em      timestamptz NOT NULL DEFAULT now(),
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (colecao, item_id),
  -- a FK é conferida como dono da tabela (fora da RLS): sem este CHECK, uma linha do inquilino A poderia apontar
  -- para uma coleção de B; com ele, o prefixo da coleção tem de ser o próprio tenant_id da linha
  CONSTRAINT ck_raster_item_prefixo CHECK (split_part(colecao, '-', 1) = tenant_id::text)
);
CREATE INDEX IF NOT EXISTS ix_raster_item_tenant ON plat.raster_item (tenant_id, colecao, estado);

ALTER TABLE plat.raster_colecao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_raster_colecao ON plat.raster_colecao;
CREATE POLICY p_raster_colecao ON plat.raster_colecao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.raster_item ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_raster_item ON plat.raster_item;
CREATE POLICY p_raster_item ON plat.raster_item FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- plat.versao_pgstac é lida por /saude e pela suíte; só o aplicador (postgres) escreve
REVOKE INSERT, UPDATE, DELETE ON plat.versao_pgstac FROM plat_app;
GRANT SELECT ON plat.versao_pgstac TO plat_app;
