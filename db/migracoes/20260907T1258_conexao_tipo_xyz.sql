-- item L6-02-g-pmtiles-xyz-tilejson: acrescenta 'xyz' ao vocabulário fechado de `plat.conexao.tipo` (030
-- já tinha 'pmtiles', sem conector; este item constrói os dois — PMTiles por URL com Range/206 conferido e
-- XYZ raster/vetor com TileJSON, ver app/conexao/ladrilhos.py). A 030 é migração legada (três dígitos,
-- IMUTÁVEL); a mudança de vocabulário entra aqui, como toda alteração de tabela já aplicada (regra da casa:
-- correção de migração aplicada é sempre arquivo novo). Idempotente: dropa e recria a mesma CHECK só se o
-- rótulo 'xyz' ainda não estiver nela.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'conexao_tipo_check'
      AND pg_get_constraintdef(oid) LIKE '%''xyz''%'
  ) THEN
    ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_tipo_check;
    ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tipo_check CHECK (tipo IN (
      'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'xyz',
      'postgres_fdw', 's3', 'http'
    ));
  END IF;
END $$;
