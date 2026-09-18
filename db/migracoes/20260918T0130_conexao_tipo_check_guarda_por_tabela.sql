-- 20260918T0130_conexao_tipo_check_guarda_por_tabela: a migração 20260916T1530 nunca chegou a rodar na
-- maioria das bases, e o motivo é a GUARDA dela, não a lista.
--
-- A 20260916T1530 decide se precisa recriar a restrição com
--     SELECT 1 FROM pg_constraint WHERE conname = 'conexao_tipo_check' AND pg_get_constraintdef(oid) LIKE ...
-- sem amarrar a qual TABELA a restrição pertence. `pg_constraint` é do BANCO inteiro, e esta instalação tem
-- a mesma restrição em dezenas de schemas (um por trilha de agente). Medido em 18/09/2026: 37 restrições
-- com esse nome no banco; UMA delas (a de uma trilha) já tinha 'xyz', 'google_sheets' e 'odk_central' —
-- e foi ela que satisfez o EXISTS, fazendo o `DO` virar no-op em TODAS as outras, inclusive no schema de
-- produção `plat`, que até agora seguia sem 'xyz' e sem 'google_sheets'.
--
-- Sintoma medido: POST /api/conexoes com tipo 'xyz' respondia 422 `conexao_tipo_check`
-- (tests/api/conexao/test_pmtiles_xyz_tilejson.py, 2 failed) — item L6-02-g-pmtiles-xyz-tilejson.
--
-- Conserto: a MESMA lista, com a guarda amarrada a `plat.conexao` por `conrelid`. A lista continua tendo
-- de ser igual à de `app/limites.py::CONEXAO_TIPOS` — as duas mudam juntas. Idempotente; sem BEGIN/COMMIT.
-- depende: 20260916T1530_conexao_tipo_check_conserto_fusao.sql

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'conexao_tipo_check'
      AND conrelid = 'plat.conexao'::regclass
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
