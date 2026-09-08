-- Fixture do item L6-02-j-bancos-externos: acrescenta ao banco docker de `tests/api/dados_pgfdw_amostra.sql`
-- (imagem `postgis/postgis:16-3.4-alpine`, porta 127.0.0.1:55499, banco `amostra_aberta`) uma tabela PostGIS e
-- uma tabela grande sem geometria. Dado sintético (nenhuma base real), só para medir o conector e a consulta.
--   docker run -d --name plat-il004ifonte-pg -p 127.0.0.1:55499:5432 -e POSTGRES_USER=leitor_amostra \
--     -e POSTGRES_PASSWORD=amostra123 -e POSTGRES_DB=amostra_aberta postgis/postgis:16-3.4-alpine
--   docker exec -i plat-il004ifonte-pg psql -U leitor_amostra -d amostra_aberta < tests/api/dados_pgfdw_amostra.sql
--   docker exec -i plat-il004ifonte-pg psql -U leitor_amostra -d amostra_aberta < tests/api/dados_bancos_externos_amostra.sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS public.sedes_municipais (
  id          serial PRIMARY KEY,
  codigo_ibge text NOT NULL,
  nome        text NOT NULL,
  geom        geometry(Point, 4674) NOT NULL
);
INSERT INTO public.sedes_municipais (codigo_ibge, nome, geom)
SELECT '35' || lpad(i::text, 5, '0'), 'sede ' || i,
       ST_SetSRID(ST_MakePoint(-46 - random() * 3, -23 + random() * 2), 4674)
FROM generate_series(1, 1000) i
WHERE NOT EXISTS (SELECT 1 FROM public.sedes_municipais);
CREATE TABLE IF NOT EXISTS public.tabela_grande (id bigint NOT NULL);
INSERT INTO public.tabela_grande SELECT generate_series(1, 2000000)
WHERE NOT EXISTS (SELECT 1 FROM public.tabela_grande);
GRANT SELECT ON public.sedes_municipais, public.tabela_grande TO ro_amostra;
