-- reaplicavel
-- 20260916T0845_rede_menor_caminho_pgrouting_public: plat.rede_menor_caminho() (criada por
-- 20260906T2126_rede_modelo_elementos.sql, item L4-01-modelo-rede) chama `plat.pgr_dijkstra`, mas
-- `CREATE EXTENSION IF NOT EXISTS pgrouting WITH SCHEMA plat` daquela migração é NO-OP em qualquer
-- base onde a extensão já existia em `public` antes dela rodar — o `IF NOT EXISTS` olha só o NOME da
-- extensão, nunca o schema pedido. Medido na trilha uniao: pgRouting 4.0.1 já estava em `public`
-- (`\df pgr_dijkstra` só lista em public; pg_extension.extnamespace = 'public'), então a chamada
-- qualificada como `plat.pgr_dijkstra` nunca existiu — 100% das chamadas de
-- test_pgrouting_resolve_menor_caminho falhavam com UndefinedFunction.
--
-- Decisão do gerente (G5, laco/handoffs/T9/FASE1.md): NÃO mover a extensão de schema (banco
-- compartilhado com outros schemas/trilhas na mesma instância; mover exige superusuário e pode
-- quebrar quem já usa pgRouting de `public`). Em vez disso, a função passa a chamar `public.pgr_*`
-- explicitamente — o mesmo padrão que app/rede_utilidades/{direcao,isolamento,lacos,tracado}.py já
-- usam para as MESMAS funções pelo lado Python (nenhum deles depende de search_path).
--
-- Único ajuste: a chamada a pgr_dijkstra recebe o schema explícito. Nenhuma outra linha da função
-- muda (mesmo corpo de 20260906T2126). CREATE OR REPLACE é idempotente; sem BEGIN/COMMIT; aplicada
-- como postgres.
-- depende: 20260906T2126_rede_modelo_elementos.sql

CREATE OR REPLACE FUNCTION plat.rede_menor_caminho(p_rede uuid, p_de uuid, p_para uuid)
RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
  v_de_seq bigint;
  v_para_seq bigint;
  v_grafo text;
  v_custo double precision := 0;
  v_sem_custo int := 0;
  v_arestas jsonb := '[]'::jsonb;
  v_n int := 0;
BEGIN
  SELECT seq INTO v_de_seq FROM plat.rede_no WHERE id = p_de AND rede_id = p_rede;
  SELECT seq INTO v_para_seq FROM plat.rede_no WHERE id = p_para AND rede_id = p_rede;
  IF v_de_seq IS NULL OR v_para_seq IS NULL THEN
    RAISE EXCEPTION 'menor_caminho_no_fora_da_rede: origem e destino precisam ser nós da mesma rede';
  END IF;

  -- o SQL do grafo vai como texto (o pgRouting executa a consulta no servidor): rede filtrada pelo
  -- literal da função, nó 'aberto' exclui toda aresta que o toca, ramal sem geometria custa 0 e é
  -- contado à parte abaixo, para que um caminho barato demais nunca pareça medição.
  v_grafo := format(
    'SELECT a.seq AS id, a.no_origem_seq AS source, a.no_destino_seq AS target, '
    'COALESCE(a.comprimento_m, 0)::float8 AS cost, COALESCE(a.comprimento_m, 0)::float8 AS reverse_cost '
    'FROM plat.rede_aresta a WHERE a.rede_id = %L::uuid '
    'AND NOT EXISTS (SELECT 1 FROM plat.rede_no n WHERE n.rede_id = a.rede_id AND n.estado = ''aberto'' '
    '  AND (n.id = a.no_origem_id OR n.id = a.no_destino_id))', p_rede);

  WITH dij AS (
    SELECT d.node, d.edge, d.seq AS ordem FROM public.pgr_dijkstra(v_grafo, v_de_seq, v_para_seq, directed := false) d
  )
  SELECT count(*),
         COALESCE(sum(COALESCE(a.comprimento_m, 0)) FILTER (WHERE a.seq IS NOT NULL), 0),
         COALESCE(sum((a.comprimento_m IS NULL)::int) FILTER (WHERE a.seq IS NOT NULL), 0),
         COALESCE(jsonb_agg(jsonb_build_object('ordem', dij.ordem, 'no_seq', dij.node, 'aresta_seq', dij.edge,
                            'custo_aresta_m', a.comprimento_m) ORDER BY dij.ordem)
                  FILTER (WHERE dij.edge > 0), '[]'::jsonb)
    INTO v_n, v_custo, v_sem_custo, v_arestas
    FROM dij LEFT JOIN plat.rede_aresta a ON a.rede_id = p_rede AND a.seq = dij.edge;

  IF v_n = 0 THEN
    RETURN jsonb_build_object('encontrado', false, 'custo_m', NULL, 'ramais_sem_custo', 0, 'arestas', '[]'::jsonb);
  END IF;
  RETURN jsonb_build_object('encontrado', true, 'custo_m', v_custo, 'ramais_sem_custo', v_sem_custo,
                            'arestas', v_arestas);
END;
$fn$;
