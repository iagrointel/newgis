-- 20260916T1530_conexao_tipo_check_conserto_fusao: conserta `plat.conexao_tipo_check` (achado tests/api/
-- conexao/, 26 falhas pré-existentes registradas no laudo do agente em wt/f2fixfdwpool).
--
-- Três migrações recentes disputaram a MESMA constraint, cada uma dropando e recriando com a lista que
-- enxergava na sua própria história de ramo, sem repartir a partir de uma fonte única:
--   20260906T2136_conexao_google_sheets.sql  -> acrescentou 'google_sheets', sem 'xyz'
--   20260907T1258_conexao_tipo_xyz.sql       -> acrescentou 'xyz' (idempotente: só recria se 'xyz' faltar)
--   20260908T1104_odk_ponte.sql              -> acrescentou 'odk_central', recriou incondicionalmente e
--                                                DERRUBOU 'xyz' e 'google_sheets' de novo (a mais recente
--                                                das três venceu — é a que a base carrega hoje).
--
-- Regra da casa (comentário verbatim da 20260908T1104): "o tipo novo de conexão entra no CHECK de 030 (a
-- lista tem de continuar igual à de app/limites.py CONEXAO_TIPOS — as duas mudam juntas)". Esta migração é a
-- ÚNICA fonte de verdade a partir de agora: a lista abaixo é exatamente `app/limites.py CONEXAO_TIPOS`
-- (deduplicada) no dia desta migração. Idempotente (recria só se algo faltar); sem BEGIN/COMMIT.
-- depende: 20260908T1104_odk_ponte.sql

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'conexao_tipo_check'
      AND pg_get_constraintdef(oid) LIKE '%''xyz''%'
      AND pg_get_constraintdef(oid) LIKE '%''google_sheets''%'
      AND pg_get_constraintdef(oid) LIKE '%''odk_central''%'
  ) THEN
    ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_tipo_check;
    ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tipo_check CHECK (tipo IN (
      'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'xyz',
      'postgres_fdw', 's3', 'http', 'odk_central', 'google_sheets'
    ));
  END IF;
END $$;
