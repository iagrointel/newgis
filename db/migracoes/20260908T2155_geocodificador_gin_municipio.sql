-- Item L2-11-a-geocodificacao-csv: restringe o candidato do pg_trgm AO MUNICÍPIO PEDIDO, dentro do índice.
--
-- Medido na trilha plat_til211ageoco (RR, 260.515 linhas, EXPLAIN ANALYZE de 08/09): na busca de logradouro
-- do motor.buscar (app/geocodificador/motor.py), o GIN trgm de `logradouro_norm` devolve 35.297 candidatos
-- do estado inteiro para "AVENIDA SEBASTIAO DINIZ", 32.622 morrem no recheck de similarity (116 ms) e só
-- DEPOIS o filtro `cod_municipio = ANY(...)` remove 1.060 — o planejador nunca cruza com o btree de
-- cod_municipio porque a estimativa do GIN (1.019 linhas) parece barata. Com 1.000 endereços por job, isso
-- é ~2 minutos só de recheck: o portão de 120 s do item não fecha.
--
-- Um GIN multicoluna (logradouro_norm gin_trgm_ops, cod_municipio int4_ops do btree_gin) põe a igualdade
-- de município DENTRO da varredura do índice: o recheck de similarity passa a rodar só sobre as linhas do
-- município pedido (~2,7 mil no lugar de 35 mil). Nenhuma consulta muda; os resultados são os mesmos.
-- O btree_gin é contrib do Postgres, sem dependência fora da casa; migrações rodam como postgres
-- (db/migrar.sh seção 1), então o CREATE EXTENSION é aplicável em produção pela via normal.
-- Idempotente, igual aos índices irmãos da 045.

CREATE EXTENSION IF NOT EXISTS btree_gin;

CREATE INDEX IF NOT EXISTS ix_geo_endereco_busca_mun ON plat.geo_endereco
  USING gin (logradouro_norm public.gin_trgm_ops, cod_municipio public.int4_ops);
