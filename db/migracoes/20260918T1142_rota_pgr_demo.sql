-- Rede de demonstração roteável para pgRouting (item L2-11-c-rota-matriz-isocrona).
--
-- O portão pede "pgRouting instalado (SELECT pgr_version()) e drivingDistance na rede de demonstração
-- confere com Dijkstra independente (networkx)". A rede vem do MESMO recorte OSM do serviço OSRM
-- (osrm/guarulhos.osm.pbf), carregada pelo script scripts/rota_pgr_demo_carga.py (idempotente: TRUNCATE
-- + COPY) — a migração só cria o DESENHO das duas tabelas (arestas + vértices), nunca o dado (a carga
-- lê um arquivo local, o que não cabe num arquivo .sql portável).
--
-- Desenho no padrão que as funções pgr_* esperam: arestas com id/source/target/cost/reverse_cost
-- (cost em SEGUNDOS, -1 quando o sentido é proibido — oneway do OSM) e vértices no desenho
-- <arestas>_vertices_pgr que o pgr_createTopology criaria (a topologia é montada na carga, em Python,
-- por arredondamento de coordenada — dispensa o CREATE TABLE temporário que o pgr_createTopology faria
-- e que o papel da aplicação não pode executar no schema).
--
-- Não é dado de inquilino (é a contraparte PostGIS do grafo OSRM, também aberto e sem RLS — mesmo
-- argumento de app/rede/rotas.py): por isso GRANT direto ao papel da aplicação, sem policy.

CREATE TABLE IF NOT EXISTS plat.rota_pgr_demo (
  id bigserial PRIMARY KEY,
  osm_id bigint,
  highway text,
  name text,
  oneway text,
  source bigint,
  target bigint,
  cost double precision NOT NULL,
  reverse_cost double precision NOT NULL,
  geom geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS rota_pgr_demo_geom_gix ON plat.rota_pgr_demo USING gist (geom);
CREATE INDEX IF NOT EXISTS rota_pgr_demo_source_idx ON plat.rota_pgr_demo (source);
CREATE INDEX IF NOT EXISTS rota_pgr_demo_target_idx ON plat.rota_pgr_demo (target);

CREATE TABLE IF NOT EXISTS plat.rota_pgr_demo_vertices_pgr (
  id bigserial PRIMARY KEY,
  x double precision NOT NULL,
  y double precision NOT NULL,
  the_geom geometry(Point, 4326)
);
CREATE INDEX IF NOT EXISTS rota_pgr_demo_vertices_gix ON plat.rota_pgr_demo_vertices_pgr USING gist (the_geom);

GRANT SELECT, INSERT, TRUNCATE ON plat.rota_pgr_demo TO plat_app;
GRANT SELECT, INSERT, TRUNCATE ON plat.rota_pgr_demo_vertices_pgr TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.rota_pgr_demo_id_seq TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.rota_pgr_demo_vertices_pgr_id_seq TO plat_app;
