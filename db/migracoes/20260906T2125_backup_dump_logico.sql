-- reaplicavel
-- 20260906T2125_backup_dump_logico (item L0-06-a-dump-logico; ADR docs/adr/20260906T2124-backup-logico.md).
-- Dump lógico diário (pg_dump -Fc) do schema plat e de cada d_<slug>, um arquivo por inquilino, com sha256,
-- bytes e tempo registrados aqui, retenção de 14 diários + 8 semanais, cópia para o bucket '<prefixo>backup'
-- do Garage e para destino externo S3 configurável. As funções são SECURITY DEFINER porque a tarefa roda no
-- inquilino técnico 'plataforma' mas precisa listar TODOS os inquilinos (RLS de plat.tenant só mostra a
-- própria linha) e gravar nestas tabelas em nome da plataforma. Toda função confere que o chamador está no
-- inquilino técnico 'plataforma' (mesmo padrão da recusa de jobs.expurgo, migração 006) — um admin de outro
-- inquilino não semeia linhas falsas de backup nem lê o destino (a chave do Garage fica aqui). Idempotente.

CREATE TABLE IF NOT EXISTS plat.backup (
  id              bigserial PRIMARY KEY,
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  esquema         text NOT NULL,                 -- 'plat' ou 'd_<slug>'
  inquilino_slug  text,                          -- NULL na linha do schema plat (núcleo compartilhado)
  arquivo         text NOT NULL,                 -- caminho absoluto do .dump no disco
  sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bytes           bigint NOT NULL CHECK (bytes >= 0),
  tabelas         int NOT NULL CHECK (tabelas >= 0),
  tempo_dump_s    numeric(10,2) NOT NULL CHECK (tempo_dump_s >= 0),
  semanal         boolean NOT NULL DEFAULT false,
  bucket_chave    text,                          -- chave do objeto no bucket de backup (NULL se a cópia falhou)
  externo_chave   text,                          -- chave no destino externo S3 (NULL se não configurado)
  origem          text NOT NULL DEFAULT 'manual',-- periodico | manual | teste
  criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_backup_esquema_em ON plat.backup (esquema, criado_em DESC);

ALTER TABLE plat.backup ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_backup ON plat.backup;
CREATE POLICY p_backup ON plat.backup FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- destino no Garage (bucket próprio, fora dos buckets de inquilino) + destino externo opcional; uma linha só
CREATE TABLE IF NOT EXISTS plat.backup_destino (
  unico          boolean PRIMARY KEY DEFAULT true CHECK (unico),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  bucket_id      text NOT NULL,
  alias          text NOT NULL,
  chave_id       text NOT NULL,
  chave_segredo  text NOT NULL,
  criado_em      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.backup_destino ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_backup_destino ON plat.backup_destino;
CREATE POLICY p_backup_destino ON plat.backup_destino FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- confere o inquilino técnico; usada por todas as funções abaixo
CREATE OR REPLACE FUNCTION plat.backup_confere_plataforma() RETURNS int
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  SELECT id INTO tid FROM plat.tenant WHERE slug = 'plataforma';
  IF tid IS NULL THEN
    RAISE EXCEPTION 'inquilino técnico plataforma ausente (migração 004)';
  END IF;
  IF plat.tenant_atual() IS DISTINCT FROM tid THEN
    RAISE EXCEPTION 'backup_so_plataforma' USING HINT = 'a rotina de backup só roda no inquilino técnico plataforma';
  END IF;
  RETURN tid;
END $$;

-- alvos do dump: todo inquilino ativo; a existência do schema d_<slug> é conferida na hora do dump
CREATE OR REPLACE FUNCTION plat.backup_alvos() RETURNS TABLE (tenant_id int, slug text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.backup_confere_plataforma();
  RETURN QUERY SELECT t.id, t.slug FROM plat.tenant t WHERE t.ativo ORDER BY t.slug;
END $$;

-- e-mails dos superadmins ativos (notificação de falha de backup; nunca silêncio)
CREATE OR REPLACE FUNCTION plat.backup_superadmins() RETURNS TABLE (email text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  tid := plat.backup_confere_plataforma();
  RETURN QUERY SELECT u.email FROM plat.usuario u
    WHERE u.tenant_id = tid AND u.superadmin AND u.ativo AND u.email IS NOT NULL AND u.email <> '';
END $$;

CREATE OR REPLACE FUNCTION plat.backup_registrar(p_esquema text, p_slug text, p_arquivo text, p_sha256 text,
  p_bytes bigint, p_tabelas int, p_tempo_dump_s numeric, p_semanal boolean, p_bucket_chave text,
  p_externo_chave text, p_origem text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; novo bigint;
BEGIN
  tid := plat.backup_confere_plataforma();
  INSERT INTO plat.backup(tenant_id, esquema, inquilino_slug, arquivo, sha256, bytes, tabelas, tempo_dump_s,
                          semanal, bucket_chave, externo_chave, origem)
  VALUES (tid, p_esquema, p_slug, p_arquivo, p_sha256, p_bytes, p_tabelas, p_tempo_dump_s,
          p_semanal, p_bucket_chave, p_externo_chave, left(coalesce(p_origem, 'manual'), 40))
  RETURNING id INTO novo;
  RETURN novo;
END $$;

-- leitura para retenção, verificação e auditoria (mais novos primeiro)
CREATE OR REPLACE FUNCTION plat.backup_listar(p_esquema text DEFAULT NULL, p_limite int DEFAULT 10000)
RETURNS TABLE (id bigint, esquema text, inquilino_slug text, arquivo text, sha256 text, bytes bigint,
               semanal boolean, bucket_chave text, externo_chave text, criado_em timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.backup_confere_plataforma();
  RETURN QUERY SELECT b.id, b.esquema, b.inquilino_slug, b.arquivo, b.sha256, b.bytes, b.semanal,
                      b.bucket_chave, b.externo_chave, b.criado_em
    FROM plat.backup b
    WHERE p_esquema IS NULL OR b.esquema = p_esquema
    ORDER BY b.criado_em DESC, b.id DESC
    LIMIT least(greatest(p_limite, 1), 100000);
END $$;

-- retenção: apaga as linhas escolhidas pela tarefa (que já removeu arquivo e objeto) e devolve o que saiu
CREATE OR REPLACE FUNCTION plat.backup_apagar(p_ids bigint[])
RETURNS TABLE (id bigint, arquivo text, bucket_chave text, externo_chave text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.backup_confere_plataforma();
  RETURN QUERY DELETE FROM plat.backup b WHERE b.id = ANY(p_ids)
    RETURNING b.id, b.arquivo, b.bucket_chave, b.externo_chave;
END $$;

-- destino do Garage: lido/escrito pela tarefa (provisão idempotente em app/backup/destino.py)
CREATE OR REPLACE FUNCTION plat.backup_destino_ler()
RETURNS TABLE (bucket_id text, alias text, chave_id text, chave_segredo text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.backup_confere_plataforma();
  RETURN QUERY SELECT d.bucket_id, d.alias, d.chave_id, d.chave_segredo FROM plat.backup_destino d WHERE d.unico;
END $$;

CREATE OR REPLACE FUNCTION plat.backup_destino_registrar(p_bucket_id text, p_alias text, p_chave_id text,
  p_chave_segredo text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  tid := plat.backup_confere_plataforma();
  INSERT INTO plat.backup_destino(unico, tenant_id, bucket_id, alias, chave_id, chave_segredo)
  VALUES (true, tid, p_bucket_id, p_alias, p_chave_id, p_chave_segredo)
  ON CONFLICT (unico) DO NOTHING;  -- a chave só nasce uma vez; o segredo do Garage nunca é devolvido de novo
END $$;

DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.backup_confere_plataforma()', 'plat.backup_alvos()', 'plat.backup_superadmins()',
    'plat.backup_registrar(text, text, text, text, bigint, int, numeric, boolean, text, text, text)',
    'plat.backup_listar(text, int)', 'plat.backup_apagar(bigint[])',
    'plat.backup_destino_ler()', 'plat.backup_destino_registrar(text, text, text, text)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
