-- reaplicavel
-- 026_jobs_manutencao_analyze (item L0-05-d, achado do testador T3: só 3 periódicos estavam registrados —
-- expurgo diário/lixeira diária/versões diárias — e o portão exige 5). ANALYZE não pode rodar como plat_app
-- (dono das tabelas é postgres; MAINTAIN nem existe nesta versão do Postgres), então a função roda SECURITY
-- DEFINER e recusa nome de tabela fora da lista de `pg_tables` do schema plat (mesmo com %I não há injeção,
-- porque o identificador só é usado depois de confirmado ali). Idempotente (só CREATE OR REPLACE, sem dado).

CREATE OR REPLACE FUNCTION plat.manutencao_analyze(
  p_tabelas text[] DEFAULT ARRAY['job', 'job_log', 'item', 'item_versao', 'agenda', 'usuario', 'evento']
) RETURNS text[] LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t text; feitas text[] := '{}';
BEGIN
  FOREACH t IN ARRAY coalesce(p_tabelas, '{}') LOOP
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'plat' AND tablename = t) THEN
      EXECUTE format('ANALYZE plat.%I', t);
      feitas := array_append(feitas, t);
    END IF;
  END LOOP;
  RETURN feitas;
END $$;

REVOKE EXECUTE ON FUNCTION plat.manutencao_analyze(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.manutencao_analyze(text[]) TO plat_app;
