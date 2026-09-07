-- 20260906T2226_rede_osm_power: conector OpenStreetMap power=* (item L4-05-g-osm-power;
-- ADR docs/adr/20260906T2226-conector-osm-power.md). Depende do modelo de elementos (a rede de
-- negócio onde o extrato vira nós e arestas) e do catálogo do pacote (os tipos eletrica-br).
-- depende: 20260906T2126_rede_modelo_elementos.sql
--
-- O que muda:
--   1. `plat.rede_importacao.fonte` passa a aceitar 'osm' (antes só 'bdgd'): a auditoria do
--      conector grava na MESMA tabela que a da BDGD — uma fonte a mais, não um modelo paralelo.
--   2. Três colunas novas na auditoria: `licenca` (a licença da fonte, exibida na ficha — no OSM
--      é a ODbL), `aviso` (a ressalva que a ficha mostra sempre — "cadastro comunitário, não
--      oficial") e `municipio` (o recorte territorial da importação; a BDGD deixa NULL, o recorte
--      dela é a distribuidora). NULL nas linhas já existentes = "fonte sem licença/aviso declarado
--      na importação", nunca inferência depois do fato.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.rede_importacao DROP CONSTRAINT IF EXISTS rede_importacao_fonte_check;
ALTER TABLE plat.rede_importacao ADD CONSTRAINT rede_importacao_fonte_check
  CHECK (fonte IN ('bdgd', 'osm'));

ALTER TABLE plat.rede_importacao ADD COLUMN IF NOT EXISTS licenca text;
ALTER TABLE plat.rede_importacao ADD COLUMN IF NOT EXISTS aviso text;
ALTER TABLE plat.rede_importacao ADD COLUMN IF NOT EXISTS municipio text;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/importar_osm', 'rede montada a partir de extrato OpenStreetMap power=* (município, contagens conferidas, desvios)')
ON CONFLICT (nome) DO NOTHING;
