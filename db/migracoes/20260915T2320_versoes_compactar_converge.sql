-- 20260915T2320_versoes_compactar_converge
--
-- Achado G2-3 (laco/handoffs/T3/ataque-g2-ADVERSARIO.md; ADR docs/adr/20260906T1623-consertos-do-ataque-g2.md
-- seção 1): `plat.item_versoes_compactar(item, manter)` fazia UMA passada de compactação em blocos de 10 e
-- devolvia até `manter + teto((N - manter) / 10)` linhas (66 com 200 PUTs, 146 com 1.000) — muito acima do
-- teto de 50 linhas que a refutação do item L0-03-l promete, porque o periódico só reaplicava a função uma
-- vez por hora e cada passada reduz o excedente por um fator de ~10, não a zero.
--
-- Remédio, dentro da PRÓPRIA função (o ADR original cogitou repetir a chamada pelo lado do Python; aqui a
-- convergência fica embutida na função, então UMA chamada — direta ou pela tarefa do job — já entrega o
-- teto, sem depender de quantas vezes o periódico rodar):
--   1. o corte que separa "recente" de "compactável" passa a ser OFFSET (p_manter - 1), não p_manter: a
--      última linha recente é substituída pela linha-resumo, então o total final é `(manter - 1) + 1 =
--      manter` — não mais `manter + 1`.
--   2. a passada de compactação (blocos de 10, preservando a granularidade histórica de cada bloco) roda
--      dentro de um LOOP que repete até uma rodada não remover nada — o mesmo algoritmo de antes, só que
--      convergido ali dentro em vez de precisar de várias invocações externas.
--
-- Com N=201 (200 PUTs) e manter=50: convergia em 66 linhas numa passada; agora convergem para 50 (49
-- recentes + 1 linha `compactada` que resume as 152 mais antigas) na mesma chamada — prova em
-- tests/api/catalogo/test_adversario_g2.py::test_g2_3_compactacao_mantem_no_maximo_50_linhas.
-- Não mexe na checagem de inquilino (achado G2-1/G2-2, já corrigida pela 20260906T1601): a linha
-- `RETURN 0` para item de outro inquilino continua antes de qualquer corte ou loop.

CREATE OR REPLACE FUNCTION plat.item_versoes_compactar(p_item uuid, p_manter int DEFAULT 50) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  corte int; removidas int := 0; removidas_rodada int; r record; n int;
  t_ctx int := plat.tenant_atual(); t_plataforma boolean;
BEGIN
  PERFORM plat.argumento_no_minimo(p_manter, 1, 'p_manter');
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = p_item AND (t_plataforma OR i.tenant_id = t_ctx)) THEN
    RETURN 0;   -- item de outro inquilino (ou inexistente): nada a fazer, sem revelar qual dos dois
  END IF;
  LOOP
    -- OFFSET (p_manter - 1): a linha-resumo final ocupa uma das `manter` vagas, não uma a mais
    SELECT versao INTO corte FROM plat.item_versao WHERE item_id = p_item
      ORDER BY versao DESC OFFSET (p_manter - 1) LIMIT 1;
    EXIT WHEN corte IS NULL;   -- já cabe em p_manter linhas, nada a compactar
    removidas_rodada := 0;
    FOR r IN SELECT array_agg(versao ORDER BY versao) AS vs, max(versao) AS topo,
                    sum(greatest(compactou, 1))::int AS resumidas
             FROM (SELECT versao, compactou, (row_number() OVER (ORDER BY versao) - 1) / 10 AS grupo
                   FROM plat.item_versao WHERE item_id = p_item AND versao <= corte) x
             GROUP BY grupo HAVING count(*) > 1 LOOP
      DELETE FROM plat.item_versao WHERE item_id = p_item AND versao = ANY (r.vs) AND versao <> r.topo;
      GET DIAGNOSTICS n = ROW_COUNT;
      removidas := removidas + n;
      removidas_rodada := removidas_rodada + n;
      UPDATE plat.item_versao SET rotulo = 'compactada', compactou = r.resumidas
        WHERE item_id = p_item AND versao = r.topo;
    END LOOP;
    EXIT WHEN removidas_rodada = 0;   -- estabilizou: só sobrou 1 linha compactável, convergiu
  END LOOP;
  RETURN removidas;
END $$;
