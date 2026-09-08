\set ON_ERROR_STOP on
\timing off
DROP SCHEMA IF EXISTS med0004 CASCADE;
CREATE SCHEMA med0004;
SET search_path = med0004, public;
-- configuração de busca: portuguese + unaccent
CREATE TEXT SEARCH CONFIGURATION med0004.pt_sem_acento (COPY = pg_catalog.portuguese);
ALTER TEXT SEARCH CONFIGURATION med0004.pt_sem_acento
  ALTER MAPPING FOR hword, hword_part, word, asciiword, asciihword, hword_asciipart WITH unaccent, portuguese_stem;
CREATE FUNCTION med0004.tags_texto(text[]) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$ SELECT array_to_string($1, ' ') $f$;
CREATE TABLE item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id int NOT NULL,
  tipo text NOT NULL,
  titulo text NOT NULL,
  resumo text,
  descricao text,
  tags text[] NOT NULL DEFAULT '{}',
  dono_id int NOT NULL,
  nivel text NOT NULL,
  status text,
  modificado_em timestamptz NOT NULL DEFAULT now(),
  apagado_em timestamptz,
  busca tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('med0004.pt_sem_acento', coalesce(titulo,'')), 'A') ||
    setweight(to_tsvector('med0004.pt_sem_acento', coalesce(med0004.tags_texto(tags),'')), 'B') ||
    setweight(to_tsvector('med0004.pt_sem_acento', coalesce(resumo,'')), 'C') ||
    setweight(to_tsvector('med0004.pt_sem_acento', coalesce(descricao,'')), 'D')) STORED
);
INSERT INTO item (tenant_id, tipo, titulo, resumo, descricao, tags, dono_id, nivel, status, modificado_em)
SELECT 1 + (g % 2),
       (ARRAY['camada_vetorial','raster','mapa','app','painel','formulario','arquivo'])[1 + g % 7],
       (ARRAY['Município','Rodovia','Hidrografia','Setor censitário','Limite estadual','Ponto de ônibus','Área de proteção'])[1 + (g*3) % 7]
         || ' ' || (ARRAY['norte','sul','leste','oeste','centro'])[1 + g % 5] || ' ' || g,
       'Resumo do conjunto ' || g || ' com sede municipal e malha viária',
       repeat('Descrição longa do item com muitos termos repetidos sobre território, bacia, estrada e escola. ', 5) || g,
       ARRAY['ibge', (ARRAY['limites','transporte','agua','censo','ambiente'])[1 + g % 5], 'ano' || (2015 + g % 10)],
       1 + g % 40,
       (ARRAY['privado','grupos','inquilino','link'])[1 + g % 4],
       CASE WHEN g % 50 = 0 THEN 'autoritativo' WHEN g % 70 = 0 THEN 'obsoleto' END,
       now() - (g || ' minutes')::interval
FROM generate_series(1, 10000) g;
UPDATE item SET titulo = 'Município' WHERE id = (SELECT id FROM item ORDER BY modificado_em LIMIT 1);
CREATE INDEX ix_item_busca ON item USING gin (busca);
CREATE INDEX ix_item_titulo_trgm ON item USING gin (titulo gin_trgm_ops);
CREATE INDEX ix_item_tenant_tipo_mod ON item (tenant_id, tipo, modificado_em DESC) WHERE apagado_em IS NULL;
-- grupos e compartilhamento
CREATE TABLE grupo_membro (grupo_id int, usuario_id int, PRIMARY KEY (grupo_id, usuario_id));
INSERT INTO grupo_membro SELECT g, u FROM generate_series(1,50) g, generate_series(1,40) u WHERE (g*u) % 3 = 0;
CREATE TABLE item_grupo (item_id uuid REFERENCES item(id) ON DELETE CASCADE, grupo_id int, PRIMARY KEY (item_id, grupo_id));
INSERT INTO item_grupo SELECT id, 1 + (abs(hashtext(id::text)) % 50) FROM item WHERE nivel = 'grupos';
CREATE INDEX ix_item_grupo_grupo ON item_grupo (grupo_id);
-- relações
CREATE TABLE item_relacao (origem uuid REFERENCES item(id) ON DELETE CASCADE, destino uuid REFERENCES item(id) ON DELETE CASCADE, tipo text, PRIMARY KEY (origem, destino, tipo));
INSERT INTO item_relacao
SELECT a.id, b.id, 'camada_de_mapa'
FROM (SELECT id, row_number() OVER () rn FROM item) a
JOIN (SELECT id, row_number() OVER () rn FROM item) b ON b.rn = ((a.rn * 7 + 13) % 10000) + 1
UNION ALL
SELECT a.id, b.id, 'mapa_de_app'
FROM (SELECT id, row_number() OVER () rn FROM item) a
JOIN (SELECT id, row_number() OVER () rn FROM item) b ON b.rn = ((a.rn * 11 + 5) % 10000) + 1
UNION ALL
SELECT a.id, b.id, 'estilo_de_camada'
FROM (SELECT id, row_number() OVER () rn FROM item) a
JOIN (SELECT id, row_number() OVER () rn FROM item) b ON b.rn = ((a.rn * 3 + 101) % 10000) + 1;
CREATE INDEX ix_item_relacao_destino ON item_relacao (destino);
ANALYZE item; ANALYZE item_grupo; ANALYZE grupo_membro; ANALYZE item_relacao;
SELECT count(*) AS itens, (SELECT count(*) FROM item_relacao) AS relacoes, (SELECT count(*) FROM item_grupo) AS compart_grupo FROM item;

CREATE OR REPLACE FUNCTION med0004.medir(q text, n int DEFAULT 30) RETURNS TABLE (p50_ms numeric, p95_ms numeric, linhas bigint) LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz; tempos numeric[] := '{}'; k bigint; BEGIN
  FOR i IN 1..n LOOP
    t0 := clock_timestamp();
    EXECUTE 'SELECT count(*) FROM (' || q || ') s' INTO k;
    tempos := tempos || round(extract(epoch FROM clock_timestamp() - t0) * 1000, 2);
  END LOOP;
  RETURN QUERY SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY v))::numeric, (percentile_cont(0.95) WITHIN GROUP (ORDER BY v))::numeric, k FROM unnest(tempos) v;
END $$;

\echo '--- FTS: municipio (sem acento) acha Município; ordenação ts_rank + modificado_em, 50 primeiros'
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND busca @@ to_tsquery('med0004.pt_sem_acento', 'municipio') ORDER BY ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','municipio')) DESC, modificado_em DESC LIMIT 50$$);
\echo '--- FTS: só ts_rank_cd: o item com título exatamente Município vem em 1º?'
SELECT titulo, ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','municipio')) r FROM item WHERE busca @@ to_tsquery('med0004.pt_sem_acento','municipio') ORDER BY r DESC, modificado_em DESC LIMIT 3;
\echo '--- FTS: com chave de título exato (unaccent+lower) antes do ts_rank_cd'
SELECT titulo, ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','municipio')) r FROM item WHERE busca @@ to_tsquery('med0004.pt_sem_acento','municipio') ORDER BY (lower(unaccent(titulo)) = lower(unaccent('municipio'))) DESC, r DESC, modificado_em DESC LIMIT 3;
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND busca @@ to_tsquery('med0004.pt_sem_acento', 'municipio') ORDER BY (lower(unaccent(titulo)) = 'municipio') DESC, ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','municipio')) DESC, modificado_em DESC LIMIT 50$$);
\echo '--- status autoritativo sobe: peso declarado 0.25 somado ao ts_rank_cd (medido)'
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND busca @@ to_tsquery('med0004.pt_sem_acento', 'rodovia') ORDER BY (lower(unaccent(titulo)) = 'rodovia') DESC, ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','rodovia')) + CASE status WHEN 'autoritativo' THEN 0.25 WHEN 'obsoleto' THEN -0.25 ELSE 0 END DESC, modificado_em DESC LIMIT 50$$);
\echo '--- filtro por bbox (extent geometry 4326, GIST) combinado com tipo'
ALTER TABLE item ADD COLUMN extent geometry(Polygon, 4326);
UPDATE item SET extent = ST_MakeEnvelope(-60 + (abs(hashtext(id::text)) % 25), -30 + (abs(hashtext(id::text)) % 25), -59 + (abs(hashtext(id::text)) % 25), -29 + (abs(hashtext(id::text)) % 25), 4326);
CREATE INDEX ix_item_extent ON item USING gist (extent);
ANALYZE item;
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND extent && ST_MakeEnvelope(-50,-20,-45,-15,4326) ORDER BY modificado_em DESC LIMIT 50$$);
\echo '--- cursor (keyset) vs deslocamento na página 100 (5.000 itens adiante)'
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 ORDER BY modificado_em DESC, id DESC OFFSET 4950 LIMIT 50$$);
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND (modificado_em, id) < ((SELECT modificado_em FROM item WHERE tenant_id = 1 ORDER BY modificado_em DESC OFFSET 4950 LIMIT 1), '00000000-0000-0000-0000-000000000000'::uuid) ORDER BY modificado_em DESC, id DESC LIMIT 50$$);
\echo '--- FTS: "Município" (com acento e maiúscula) acha os mesmos?'
SELECT count(*) AS com_acento FROM item WHERE busca @@ to_tsquery('med0004.pt_sem_acento', 'Município');
SELECT count(*) AS sem_acento FROM item WHERE busca @@ to_tsquery('med0004.pt_sem_acento', 'municipio');
\echo '--- trigram: municpio (erro de digitação) por similaridade no título, 50 primeiros'
SET pg_trgm.similarity_threshold = 0.3;
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND titulo % 'municpio' ORDER BY similarity(titulo, 'municpio') DESC LIMIT 50$$);
SELECT count(*) AS acha_trgm FROM item WHERE titulo % 'municpio';
\echo '--- lista por tipo (sem busca), 50 primeiros por modificado_em'
SELECT * FROM medir($$SELECT id FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND tipo = 'mapa' ORDER BY modificado_em DESC LIMIT 50$$);
\echo '--- lista por tipo com total (count separado)'
SELECT * FROM medir($$SELECT count(*) FROM item WHERE apagado_em IS NULL AND tenant_id = 1 AND tipo = 'mapa'$$);
\echo '--- pode_ler por EXISTS (usuário 7, sem cache): varrer os 10 mil e contar visíveis'
SELECT * FROM medir($$SELECT i.id FROM item i WHERE i.apagado_em IS NULL AND i.tenant_id = 1 AND (i.nivel = 'inquilino' OR i.dono_id = 7 OR (i.nivel = 'grupos' AND EXISTS (SELECT 1 FROM item_grupo ig JOIN grupo_membro gm ON gm.grupo_id = ig.grupo_id AND gm.usuario_id = 7 WHERE ig.item_id = i.id)))$$, 20);
\echo '--- pode_ler + busca + ordenação, 50 primeiros'
SELECT * FROM medir($$SELECT i.id FROM item i WHERE i.apagado_em IS NULL AND i.tenant_id = 1 AND busca @@ to_tsquery('med0004.pt_sem_acento','rodovia') AND (i.nivel = 'inquilino' OR i.dono_id = 7 OR (i.nivel = 'grupos' AND EXISTS (SELECT 1 FROM item_grupo ig JOIN grupo_membro gm ON gm.grupo_id = ig.grupo_id AND gm.usuario_id = 7 WHERE ig.item_id = i.id))) ORDER BY ts_rank_cd(busca, to_tsquery('med0004.pt_sem_acento','rodovia')) DESC, modificado_em DESC LIMIT 50$$);
\echo '--- usado_por profundidade 2 (recursivo, índice em destino) para 1 item'
SELECT * FROM medir($$WITH RECURSIVE dep AS (SELECT origem, destino, tipo, 1 AS prof FROM item_relacao WHERE destino = (SELECT id FROM item OFFSET 4321 LIMIT 1) UNION ALL SELECT r.origem, r.destino, r.tipo, d.prof + 1 FROM item_relacao r JOIN dep d ON r.destino = d.origem WHERE d.prof < 2) SELECT * FROM dep$$);
\echo '--- ordem de exclusão: fecho transitivo completo (dependentes de dependentes) de 1 item, com corte de ciclo por caminho'
SELECT * FROM medir($$WITH RECURSIVE dep AS (SELECT origem, destino, 1 AS prof, ARRAY[destino, origem] AS caminho FROM item_relacao WHERE destino = (SELECT id FROM item OFFSET 4321 LIMIT 1) UNION ALL SELECT r.origem, r.destino, d.prof + 1, d.caminho || r.origem FROM item_relacao r JOIN dep d ON r.destino = d.origem WHERE NOT r.origem = ANY(d.caminho) AND d.prof < 6) SELECT DISTINCT origem FROM dep$$, 10);
\echo '--- custo de escrita: UPDATE de título em 1 item (recalcula tsvector + 2 índices GIN)'
SELECT * FROM medir($$WITH u AS (UPDATE item SET titulo = titulo || ' x' WHERE id = (SELECT id FROM item OFFSET 100 LIMIT 1) RETURNING id) SELECT id FROM u$$, 20);
\echo '--- tamanho'
SELECT pg_size_pretty(pg_total_relation_size('item')) AS item_total, pg_size_pretty(pg_relation_size('ix_item_busca')) AS gin_busca, pg_size_pretty(pg_relation_size('ix_item_titulo_trgm')) AS gin_trgm;
DROP SCHEMA med0004 CASCADE;
SELECT 'schema med0004 apagado' AS fim;
