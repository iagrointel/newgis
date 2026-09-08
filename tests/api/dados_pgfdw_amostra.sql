-- Segundo banco Postgres de teste do item L0-04-i-fonte-registrada (tests/api/test_pgfdw.py).
-- Dado aberto sintético no formato IBGE (estados/municípios/série de precipitação mensal) — nunca dado real
-- de cliente/parceiro. Rodar dentro do container depois de criá-lo:
--
--   docker run -d --name plat-il004ifonte-pg -e POSTGRES_PASSWORD=amostra123 -e POSTGRES_USER=leitor_amostra \
--     -e POSTGRES_DB=amostra_aberta -p 127.0.0.1:55499:5432 postgres:16-alpine
--   docker exec -i plat-il004ifonte-pg psql -U leitor_amostra -d amostra_aberta < tests/api/dados_pgfdw_amostra.sql

CREATE TABLE IF NOT EXISTS public.estados (
  sigla text PRIMARY KEY,
  nome text NOT NULL,
  regiao text NOT NULL,
  populacao_2022 bigint
);
INSERT INTO public.estados VALUES
  ('SP', 'São Paulo', 'Sudeste', 44411238),
  ('RJ', 'Rio de Janeiro', 'Sudeste', 16054524),
  ('MG', 'Minas Gerais', 'Sudeste', 20539989)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS public.municipios (
  codigo_ibge int PRIMARY KEY,
  nome text NOT NULL,
  uf text NOT NULL,
  populacao_2022 int
);
INSERT INTO public.municipios VALUES
  (3550308, 'São Paulo', 'SP', 11451999),
  (3304557, 'Rio de Janeiro', 'RJ', 6211423),
  (3106200, 'Belo Horizonte', 'MG', 2315560)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS public.precipitacao_mensal (
  id serial PRIMARY KEY,
  codigo_ibge int NOT NULL,
  mes date NOT NULL,
  mm numeric(6, 1)
);
INSERT INTO public.precipitacao_mensal (codigo_ibge, mes, mm)
SELECT 3550308, '2026-01-01'::date, 210.4
WHERE NOT EXISTS (SELECT 1 FROM public.precipitacao_mensal WHERE codigo_ibge = 3550308 AND mes = '2026-01-01');
INSERT INTO public.precipitacao_mensal (codigo_ibge, mes, mm)
SELECT 3550308, '2026-02-01'::date, 180.2
WHERE NOT EXISTS (SELECT 1 FROM public.precipitacao_mensal WHERE codigo_ibge = 3550308 AND mes = '2026-02-01');
INSERT INTO public.precipitacao_mensal (codigo_ibge, mes, mm)
SELECT 3304557, '2026-01-01'::date, 145.9
WHERE NOT EXISTS (SELECT 1 FROM public.precipitacao_mensal WHERE codigo_ibge = 3304557 AND mes = '2026-01-01');

-- papel só-leitura, não-superuser (usado no fluxo principal do portão; o superuser leitor_amostra/amostra123
-- do POSTGRES_USER acima serve só ao teste do adversário "registra com usuário superuser")
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ro_amostra') THEN
    CREATE ROLE ro_amostra LOGIN PASSWORD 'ro123456' NOSUPERUSER;
  END IF;
END $$;
GRANT CONNECT ON DATABASE amostra_aberta TO ro_amostra;
GRANT USAGE ON SCHEMA public TO ro_amostra;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ro_amostra;
