-- 022_arquivos: armazenamento de objetos por inquilino no Garage (item L0-11-arquivos-objetos; ADR 0006, que
-- estende o contrato do ADR 0004 seção 11.3 e do ADR 0005 seção 11.3-estendida). plat.arquivo_bucket guarda o
-- bucket/chaves S3 (RW nunca sai da API; RO reservada ao L1-02/tiles) e a cota espelhada de tenant.cota_bytes;
-- plat.arquivo é o metadado (content-type, sha256, bytes) de cada objeto gravado, para a varredura de órfãos.
-- As duas funções SECURITY DEFINER resolvem/gravam o bucket ANTES de existir contexto de inquilino na conexão
-- (mesmo padrão de auth_* do ADR 0001 seção 3.3: app/objetos.py abre conexão própria para servir a URL assinada
-- anônima, que não passa por db.db(ctx)). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.arquivo_bucket (
  tenant_id         int PRIMARY KEY REFERENCES plat.tenant(id),
  bucket_id         text NOT NULL,               -- id do bucket no Garage (hex)
  bucket_alias      text NOT NULL UNIQUE,        -- 'plat-<slug>' (settings.PLAT_GARAGE_BUCKET_PREFIXO + slug)
  chave_rw_id       text NOT NULL,
  chave_rw_segredo  text NOT NULL,                -- só a API usa; nunca entregue ao navegador
  chave_ro_id       text NOT NULL,
  chave_ro_segredo  text NOT NULL,                -- reservada ao L1-02 (tiles); nunca entregue ao navegador
  cota_bytes        bigint NOT NULL,
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  criado_em         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plat.arquivo (
  id            bigserial PRIMARY KEY,
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  classe        text NOT NULL,               -- 'miniatura' | 'exportacao' | 'objeto' | ... (livre, sem vocabulário fechado)
  referencia    text,                        -- uuid do item/job dono, quando houver (NULL = objeto genérico por sha256)
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bytes         bigint NOT NULL CHECK (bytes >= 0),
  content_type  text NOT NULL,
  chave         text NOT NULL,               -- '<slug>/<classe>/[<referencia>/]<sha256>.<ext>' (a chave devolvida ao chamador)
  criado_por    int REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  apagado_em    timestamptz
);
-- parcial (só entre as linhas vivas): reenviar o mesmo conteúdo depois de apagado não pode violar unicidade contra
-- a linha morta; a re-gravação reaproveita a MESMA linha (UPDATE, não INSERT — ver plat.arquivo_registrar abaixo)
CREATE UNIQUE INDEX IF NOT EXISTS ix_arquivo_dedupe ON plat.arquivo (tenant_id, classe, referencia, sha256)
  WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_arquivo_tenant_criado ON plat.arquivo (tenant_id, criado_em DESC) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_arquivo_chave ON plat.arquivo (chave);

-- upload multipart em curso (contrato ADR 0005 seção 11.3-estendida: parte_iniciar/parte_enviar/parte_concluir/
-- parte_abortar); o upload_id É o UploadId do S3 do Garage, então já é opaco e único por si só.
CREATE TABLE IF NOT EXISTS plat.arquivo_upload (
  upload_id     text PRIMARY KEY,
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  classe        text NOT NULL,
  referencia    text,
  content_type  text NOT NULL,
  chave_temp    text NOT NULL,             -- caminho dentro do bucket, '_tmp/<uuid>'
  criado_em     timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.arquivo_upload ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_arquivo_upload ON plat.arquivo_upload;
CREATE POLICY p_arquivo_upload ON plat.arquivo_upload FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.arquivo_bucket ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_arquivo_bucket ON plat.arquivo_bucket;
CREATE POLICY p_arquivo_bucket ON plat.arquivo_bucket FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.arquivo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_arquivo ON plat.arquivo;
CREATE POLICY p_arquivo ON plat.arquivo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- funções SECURITY DEFINER (fora do contexto de
-- inquilino: a entrega de objeto por URL assinada, ADR 0004 11.2, é uma rota anônima sem db.db(ctx))
-- reaplicavel
CREATE OR REPLACE FUNCTION plat.arquivo_bucket_resolver(p_slug text)
RETURNS TABLE (
  tenant_id int, bucket_id text, bucket_alias text,
  chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text, cota_bytes bigint
) LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes
  FROM plat.arquivo_bucket b JOIN plat.tenant t ON t.id = b.tenant_id
  WHERE t.slug = p_slug;
$$;

-- reaplicavel
CREATE OR REPLACE FUNCTION plat.arquivo_bucket_por_tenant(p_tenant_id int)
RETURNS TABLE (
  tenant_id int, bucket_id text, bucket_alias text,
  chave_rw_id text, chave_rw_segredo text, chave_ro_id text, chave_ro_segredo text, cota_bytes bigint
) LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes
  FROM plat.arquivo_bucket b WHERE b.tenant_id = p_tenant_id;
$$;

-- reaplicavel
CREATE OR REPLACE FUNCTION plat.arquivo_bucket_registrar(
  p_tenant_id int, p_bucket_id text, p_bucket_alias text,
  p_chave_rw_id text, p_chave_rw_segredo text, p_chave_ro_id text, p_chave_ro_segredo text, p_cota_bytes bigint
) RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.arquivo_bucket
    (tenant_id, bucket_id, bucket_alias, chave_rw_id, chave_rw_segredo, chave_ro_id, chave_ro_segredo, cota_bytes)
  VALUES (p_tenant_id, p_bucket_id, p_bucket_alias, p_chave_rw_id, p_chave_rw_segredo, p_chave_ro_id,
          p_chave_ro_segredo, p_cota_bytes)
  ON CONFLICT (tenant_id) DO NOTHING;
$$;

-- reaplicavel
CREATE OR REPLACE FUNCTION plat.arquivo_bucket_cota_atualizar(p_tenant_id int, p_cota_bytes bigint)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.arquivo_bucket SET cota_bytes = p_cota_bytes, atualizado_em = now() WHERE tenant_id = p_tenant_id;
$$;

-- registro de metadado de objeto: chamada de dentro de db.db(ctx) (contexto de inquilino já presente), então usa
-- a RLS normal (INSERT direto na tabela, sem SECURITY DEFINER) — mantida aqui só para o índice ficar perto do DDL.
