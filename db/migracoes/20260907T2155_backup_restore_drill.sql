-- reaplicavel
-- 20260907T2155_backup_restore_drill (item L0-06-c-restore-drill).
-- depende: 20260906T2125_backup_dump_logico.sql
-- Ensaio de restauracao: o job backup.restore_drill restaura o ultimo dump de cada esquema num banco
-- temporario, compara COUNT(*) de todas as tabelas com coluna tenant_id contra a producao, confere o
-- sha256 de ate 3 objetos do bucket por inquilino contra o manifesto e grava o resultado aqui. Mesma
-- moldura de seguranca da migracao 20260906T2125: funcoes SECURITY DEFINER que so aceitam o inquilino
-- tecnico 'plataforma' (plat.backup_confere_plataforma), RLS na tabela, EXECUTE so para plat_app.
-- Idempotente.

CREATE TABLE IF NOT EXISTS plat.backup_drill (
  id               bigserial PRIMARY KEY,
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  backup_id        bigint,                        -- linha de plat.backup ensaiada (NULL se ja foi apagada)
  esquema          text NOT NULL,
  inquilino_slug   text,
  arquivo          text NOT NULL,
  dump_em          timestamptz NOT NULL,          -- instante do dump: a base de comparacao, nao 'agora'
  tabelas          int NOT NULL CHECK (tabelas >= 0),
  linhas           bigint NOT NULL CHECK (linhas >= 0),
  divergencias     jsonb NOT NULL DEFAULT '[]'::jsonb,
  posteriores      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- diferencas explicadas por escrita apos o dump
  objetos_conferidos int NOT NULL DEFAULT 0 CHECK (objetos_conferidos >= 0),
  ok               boolean NOT NULL,
  mensagem         text,
  duracao_drill_s  numeric(10,2) NOT NULL CHECK (duracao_drill_s >= 0),
  origem           text NOT NULL DEFAULT 'manual',
  criado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_backup_drill_em ON plat.backup_drill (criado_em DESC);

ALTER TABLE plat.backup_drill ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_backup_drill ON plat.backup_drill;
CREATE POLICY p_backup_drill ON plat.backup_drill FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

CREATE OR REPLACE FUNCTION plat.backup_drill_registrar(p_backup_id bigint, p_esquema text, p_slug text,
  p_arquivo text, p_dump_em timestamptz, p_tabelas int, p_linhas bigint, p_divergencias jsonb,
  p_posteriores jsonb, p_objetos_conferidos int, p_ok boolean, p_mensagem text, p_duracao_drill_s numeric,
  p_origem text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; novo bigint;
BEGIN
  tid := plat.backup_confere_plataforma();
  INSERT INTO plat.backup_drill(tenant_id, backup_id, esquema, inquilino_slug, arquivo, dump_em, tabelas,
                                linhas, divergencias, posteriores, objetos_conferidos, ok, mensagem,
                                duracao_drill_s, origem)
  VALUES (tid, p_backup_id, p_esquema, p_slug, p_arquivo, p_dump_em, p_tabelas, p_linhas,
          coalesce(p_divergencias, '[]'::jsonb), coalesce(p_posteriores, '[]'::jsonb),
          coalesce(p_objetos_conferidos, 0), p_ok, left(p_mensagem, 4000), p_duracao_drill_s,
          left(coalesce(p_origem, 'manual'), 40))
  RETURNING id INTO novo;
  RETURN novo;
END $$;

CREATE OR REPLACE FUNCTION plat.backup_drill_listar(p_esquema text DEFAULT NULL, p_limite int DEFAULT 100)
RETURNS TABLE (id bigint, backup_id bigint, esquema text, inquilino_slug text, arquivo text,
               dump_em timestamptz, tabelas int, linhas bigint, divergencias jsonb, posteriores jsonb,
               objetos_conferidos int, ok boolean, mensagem text, duracao_drill_s numeric,
               origem text, criado_em timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.backup_confere_plataforma();
  RETURN QUERY SELECT d.id, d.backup_id, d.esquema, d.inquilino_slug, d.arquivo, d.dump_em, d.tabelas,
                      d.linhas, d.divergencias, d.posteriores, d.objetos_conferidos, d.ok, d.mensagem,
                      d.duracao_drill_s, d.origem, d.criado_em
    FROM plat.backup_drill d
    WHERE p_esquema IS NULL OR d.esquema = p_esquema
    ORDER BY d.criado_em DESC, d.id DESC
    LIMIT least(greatest(p_limite, 1), 10000);
END $$;

-- Resumo do ultimo ensaio para a pagina de status (/saude): so agregado, sem nome de arquivo nem de
-- inquilino, por isso NAO exige o inquilino tecnico -- a sonda de status roda sem sessao.
CREATE OR REPLACE FUNCTION plat.backup_drill_status()
RETURNS TABLE (ultimo_em timestamptz, ok boolean, esquemas int, divergencias int, duracao_drill_s numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  WITH ultima AS (SELECT max(criado_em) AS em FROM plat.backup_drill),
       rodada AS (SELECT d.* FROM plat.backup_drill d, ultima u
                   WHERE u.em IS NOT NULL AND d.criado_em > u.em - interval '1 hour')
  SELECT (SELECT em FROM ultima),
         coalesce(bool_and(r.ok), true),
         count(*)::int,
         coalesce(sum(jsonb_array_length(r.divergencias))::int, 0),
         coalesce(max(r.duracao_drill_s), 0)
    FROM rodada r
$$;

DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.backup_drill_registrar(bigint, text, text, text, timestamptz, int, bigint, jsonb, jsonb, int, boolean, text, numeric, text)',
    'plat.backup_drill_listar(text, int)', 'plat.backup_drill_status()'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
