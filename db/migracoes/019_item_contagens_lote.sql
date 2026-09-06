-- reaplicavel
-- 019_item_contagens_lote (medido no L0-03, correção de desempenho pós-fechamento: GET /api/itens?tipo=mapa&limite=50
-- com o corpus de 11 mil = mediana 199,7 ms / p95 203 ms contra o portão de <100 ms). Causa medida (EXPLAIN ANALYZE +
-- profiling isolado, conexão reaproveitada): a rota de lista chamava `plat.item_contagens(uuid)` uma vez POR ITEM da
-- página (LATERAL, 50 chamadas) — mesmo padrão de N+1 que a 017 já corrigiu para `pode_ler` na política de leitura.
-- A função é STABLE mas o planejador não sabe seu custo real (estimativa default de 1.000 linhas por chamada de
-- função SQL de saída múltipla), o que infla o custo total estimado da consulta acima de jit_above_cost (100.000)
-- e força compilação JIT EM TODA CHAMADA (medido: ~40-60 ms só de JIT, "Emission" no EXPLAIN ANALYZE) — a assinatura
-- de "piso fixo por chamada" que o gerente observou (170-230 ms com pouca variação) é exatamente esse par: função
-- por linha + JIT disparado pelo custo mal estimado, não contenção de ambiente.
-- Esta migração acrescenta `plat.item_contagens_lote(uuid[])`, MESMO cálculo de plat.item_contagens (mesma política
-- de bypass: SECURITY DEFINER, dono postgres com BYPASSRLS — os contadores são "quantos no total", não "quantos
-- visíveis a mim", igual à função original), mas para cada item da página em UMA consulta agregada (GROUP BY),
-- em vez de uma chamada por linha. plat.item_contagens continua existindo e é usada pela rota de item único
-- (GET /api/itens/{id}), onde chamar uma vez não é N+1 — só a rota de LISTA passa a usar a versão em lote.
-- Idempotente (CREATE OR REPLACE + GRANT repetível).
CREATE OR REPLACE FUNCTION plat.item_contagens_lote(p_itens uuid[])
RETURNS TABLE (item_id uuid, usado_por int, criado_a_partir_de int, grupos int, links_ativos int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public ROWS 50 AS $$
  SELECT x.id,
         coalesce(up.n, 0)::int,
         coalesce(cp.n, 0)::int,
         coalesce(gr.n, 0)::int,
         coalesce(lk.n, 0)::int
  FROM unnest(p_itens) AS x(id)
  LEFT JOIN (
    SELECT r.destino AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL
    WHERE r.destino = ANY (p_itens)
    GROUP BY r.destino
  ) up ON up.id = x.id
  LEFT JOIN (
    SELECT r.origem AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL
    WHERE r.origem = ANY (p_itens)
    GROUP BY r.origem
  ) cp ON cp.id = x.id
  LEFT JOIN (
    SELECT ig.item_id AS id, count(*) AS n
    FROM plat.item_grupo ig
    WHERE ig.item_id = ANY (p_itens)
    GROUP BY ig.item_id
  ) gr ON gr.id = x.id
  LEFT JOIN (
    SELECT k.item_id AS id, count(*) AS n
    FROM plat.compartilhamento_link k
    WHERE k.item_id = ANY (p_itens) AND k.revogado_em IS NULL AND (k.expira_em IS NULL OR k.expira_em > now())
    GROUP BY k.item_id
  ) lk ON lk.id = x.id
$$;

REVOKE EXECUTE ON FUNCTION plat.item_contagens_lote(uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.item_contagens_lote(uuid[]) TO plat_app;
