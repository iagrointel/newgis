-- 20260916T0955_conserto_fusao_procedencia_arquivo_cena: 20260906T1544c24_procedencia_item.sql acrescentou a
-- propriedade `procedencia` (item L0-09-a) aos esquemas de 'raster', 'arquivo', 'vista_de_camada' e 'cena' por
-- `jsonb_set` com `esquema_versao = esquema_versao + 1`. Duas migrações posteriores no MESMO dia perderam essa
-- adição, por dois mecanismos diferentes:
--
--   - 'arquivo': 20260906T2151_exportacao_camada.sql faz `INSERT ... ON CONFLICT (nome) DO UPDATE SET esquema =
--     CASE WHEN tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN tipo_item.esquema ELSE EXCLUDED.esquema
--     END` com `EXCLUDED.esquema_versao` CRAVADO em 2 no INSERT. Como 1544c24 tinha acabado de somar 1 ao
--     esquema_versao ORIGINAL de 'arquivo' (1 -> 2), a comparação empatou (2 > 2 é falso) e o CASE escolheu
--     EXCLUDED — o esquema literal do INSERT, sem `procedencia`. Empate em esquema_versao decide para o lado
--     ERRADO (o mais novo por ordem de arquivo, não o mais completo).
--   - 'cena': 20260908T0601_cena_esquema.sql faz `UPDATE plat.tipo_item SET esquema = $esq${...}$esq$ WHERE
--     nome = 'cena'` — substitui o esquema INTEIRO, sem guarda de versão nenhuma e sem `procedencia`.
--
-- MEDIDO 16/09/2026 (tests/api/catalogo/test_procedencia.py::test_tipos_de_dado_aceitam_o_bloco[arquivo|cena]):
-- os dois tipos hoje recusam `dados.procedencia` com 422 `additionalProperties`. 'raster' e 'vista_de_camada'
-- não foram atingidos (conferido: mantêm a propriedade).
--
-- Conserto ADITIVO por `jsonb_set` (mesma receita do conserto de app/painel desta rodada): não mexe em mais
-- nada do esquema de 'arquivo'/'cena', só garante a chave. Sem mudar `esquema_versao` — a propriedade é
-- aditiva e compatível com documento antigo (nenhum documento existente grava `procedencia`, então não há
-- migração de dado). Idempotente; sem BEGIN/COMMIT.
UPDATE plat.tipo_item
SET esquema = jsonb_set(esquema, '{properties,procedencia}',
                        '{"type":["object","null"],"additionalProperties":true}'::jsonb, true)
WHERE nome IN ('arquivo', 'cena');

DO $$
DECLARE faltando text[];
BEGIN
  SELECT array_agg(nome) INTO faltando
    FROM plat.tipo_item
   WHERE nome IN ('arquivo', 'cena') AND esquema #> '{properties,procedencia}' IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'ainda sem procedencia: %', faltando;
  END IF;
END $$;
