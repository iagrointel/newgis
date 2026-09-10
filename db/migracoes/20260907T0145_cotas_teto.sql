-- 20260907T0145_cotas_teto (item L0-07-c-cotas-uso, correção pós-refutação): teto de cota IMPOSTO PELA
-- PLATAFORMA, que o próprio inquilino (privilégio org.configurar, PUT /api/org) nunca ultrapassa — só o
-- superadmin move o teto (plat.tenant_cotas_definir). Sem isso o admin do inquilino conseguia elevar a
-- própria cota_bytes/cota_usuarios sem limite (achado do adversário em 06/09 contra este mesmo item: a
-- rota PUT /api/org só tinha piso — Field(ge=...) — nunca teto). Depende da 20260906T2124_cotas_uso.sql
-- (plat.tenant_cotas_definir precisa existir para ser substituída). Idempotente. Sem BEGIN/COMMIT.
-- depende: 20260906T2124_cotas_uso.sql

-- ---------------------------------------------------------------- 1. teto de armazenamento (coluna, mesmo
-- padrão de cota_bytes): default bem acima do padrão de cota_bytes (20 GiB, migração 002) para não travar
-- nenhum inquilino existente; backfill explícito para quem já tinha a coluna com outro valor por acidente.
ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS cota_bytes_teto bigint;
UPDATE plat.tenant SET cota_bytes_teto = greatest(cota_bytes, 10995116277760) WHERE cota_bytes_teto IS NULL;
ALTER TABLE plat.tenant ALTER COLUMN cota_bytes_teto SET DEFAULT 10995116277760;
ALTER TABLE plat.tenant ALTER COLUMN cota_bytes_teto SET NOT NULL;

-- ---------------------------------------------------------------- 2. teto de usuários (config, mesmo padrão de
-- cota_usuarios): plat.cota_usuarios_teto(tenant) — default 5000 (bem acima de ORG_COTA_USUARIOS_PADRAO=2000).
CREATE OR REPLACE FUNCTION plat.cota_usuarios_teto(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_usuarios_teto')::int, 5000) FROM plat.tenant WHERE id = p_tenant
$$;
REVOKE EXECUTE ON FUNCTION plat.cota_usuarios_teto(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.cota_usuarios_teto(int) TO plat_app;

-- ---------------------------------------------------------------- 3. plat.tenant_cotas_definir ganha os dois
-- tetos (só o superadmin, via plataforma_operador, já checado na função original) e passa a EXIGIR que toda
-- cota_bytes/cota_usuarios nova (deste chamado ou já gravada) respeite o teto vigente — o invariante
-- "cota <= teto" nunca fica quebrado, mesmo quando só um dos dois é alterado no mesmo chamado.
-- Assinatura muda (2 parâmetros novos no fim): DROP explícito da versão de 6 parâmetros da 20260906T2124,
-- senão CREATE OR REPLACE com lista de argumentos diferente cria uma 2ª função sobrecarregada em vez de
-- substituir (Postgres identifica função por nome+tipos dos argumentos, não só pelo nome).
DROP FUNCTION IF EXISTS plat.tenant_cotas_definir(text, int, bigint, int, int, int);

CREATE OR REPLACE FUNCTION plat.tenant_cotas_definir(
  p_sessao_hash text, p_tenant int, p_cota_bytes bigint DEFAULT NULL,
  p_cota_usuarios int DEFAULT NULL, p_cota_itens int DEFAULT NULL, p_cota_jobs_dia int DEFAULT NULL,
  p_cota_bytes_teto bigint DEFAULT NULL, p_cota_usuarios_teto int DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  v_config jsonb := '{}'::jsonb;
  v_teto_bytes bigint;
  v_teto_usuarios int;
  v_cota_bytes_final bigint;
  v_cota_usuarios_final int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT cota_bytes, cota_bytes_teto INTO v_cota_bytes_final, v_teto_bytes FROM plat.tenant WHERE id = p_tenant;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  v_cota_usuarios_final := plat.cota_usuarios(p_tenant);
  v_teto_usuarios := plat.cota_usuarios_teto(p_tenant);

  IF p_cota_bytes IS NOT NULL AND p_cota_bytes < 104857600 THEN  -- mesmo piso de ORG_COTA_BYTES_MIN (100 MiB)
    RAISE EXCEPTION 'cota_bytes_abaixo_do_minimo';
  END IF;
  IF p_cota_bytes_teto IS NOT NULL AND p_cota_bytes_teto < 104857600 THEN
    RAISE EXCEPTION 'cota_bytes_teto_abaixo_do_minimo';
  END IF;
  IF p_cota_usuarios IS NOT NULL THEN
    IF p_cota_usuarios < 1 THEN RAISE EXCEPTION 'cota_usuarios_abaixo_do_minimo'; END IF;
    v_config := v_config || jsonb_build_object('cota_usuarios', p_cota_usuarios);
  END IF;
  IF p_cota_itens IS NOT NULL THEN
    IF p_cota_itens < 1 THEN RAISE EXCEPTION 'cota_itens_abaixo_do_minimo'; END IF;
    v_config := v_config || jsonb_build_object('catalogo', jsonb_build_object('cota_itens', p_cota_itens));
  END IF;
  IF p_cota_jobs_dia IS NOT NULL THEN
    IF p_cota_jobs_dia < 0 THEN RAISE EXCEPTION 'cota_jobs_dia_invalida'; END IF;
    v_config := v_config || jsonb_build_object('cota_jobs_dia', p_cota_jobs_dia);
  END IF;
  IF p_cota_usuarios_teto IS NOT NULL THEN
    IF p_cota_usuarios_teto < 1 THEN RAISE EXCEPTION 'cota_usuarios_teto_abaixo_do_minimo'; END IF;
    v_config := v_config || jsonb_build_object('cota_usuarios_teto', p_cota_usuarios_teto);
  END IF;

  -- invariante cota <= teto: usa o valor NOVO de cada lado quando fornecido, senão o vigente
  v_cota_bytes_final := coalesce(p_cota_bytes, v_cota_bytes_final);
  v_teto_bytes := coalesce(p_cota_bytes_teto, v_teto_bytes);
  IF v_cota_bytes_final > v_teto_bytes THEN
    RAISE EXCEPTION 'cota_bytes_acima_do_teto';
  END IF;
  v_cota_usuarios_final := coalesce(p_cota_usuarios, v_cota_usuarios_final);
  v_teto_usuarios := coalesce(p_cota_usuarios_teto, v_teto_usuarios);
  IF v_cota_usuarios_final > v_teto_usuarios THEN
    RAISE EXCEPTION 'cota_usuarios_acima_do_teto';
  END IF;

  UPDATE plat.tenant
  SET cota_bytes = coalesce(p_cota_bytes, cota_bytes),
      cota_bytes_teto = coalesce(p_cota_bytes_teto, cota_bytes_teto),
      config = config || v_config
  WHERE id = p_tenant;
END $$;

REVOKE EXECUTE ON FUNCTION plat.tenant_cotas_definir(text, int, bigint, int, int, int, bigint, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_cotas_definir(text, int, bigint, int, int, int, bigint, int) TO plat_app;

-- ---------------------------------------------------------------- 4. vocabulário de evento (ADR 0002 seção
-- 9.4, plat.evento.tipo tem FK para plat.evento_tipo — sem esta linha POST /api/plataforma/inquilinos/{id}/cotas
-- (app/auth/rotas_plataforma.py::cotas_definir, que chama registrar_evento) cai em 409 "em_uso"/evento_tipo_fkey
-- em vez de 204, mesmo achado que a 048 já documentou para outro evento).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('inquilinos/cotas', 'superadmin alterou cota ou teto de cota de um inquilino')
ON CONFLICT (nome) DO NOTHING;
