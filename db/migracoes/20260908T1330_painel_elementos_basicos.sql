-- 20260908T1330 (item L2-06-b-elementos-basicos): o documento de painel ganha os elementos que faltavam do
-- vocabulário dos Dashboards — gráfico serial, pizza/rosca, lista, mapa, detalhes, texto rico, legenda e
-- cabeçalho — ao lado dos quatro do L2-06-a (texto, indicador, gráfico, tabela). Só o ENUM de `tipo` muda:
-- `opcoes` já é `additionalProperties: true` no esquema (a forma de cada tipo é validada em código, onde ela
-- pode olhar os campos da camada). Sem mudança de `esquema_versao`: documento antigo continua válido palavra
-- por palavra, e documento novo só usa nomes que a versão anterior não conhecia.
UPDATE plat.tipo_item
SET esquema = jsonb_set(
      esquema,
      '{properties,corpo,properties,elementos,items,properties,tipo,enum}',
      '["texto","indicador","grafico","tabela","serial","pizza","lista","mapa","detalhes","texto_rico","legenda","cabecalho"]'::jsonb,
      false)
WHERE nome = 'painel'
  AND esquema #> '{properties,corpo,properties,elementos,items,properties,tipo,enum}' IS NOT NULL;

DO $$
DECLARE tipos jsonb;
BEGIN
  SELECT esquema #> '{properties,corpo,properties,elementos,items,properties,tipo,enum}'
    INTO tipos FROM plat.tipo_item WHERE nome = 'painel';
  IF tipos IS NULL OR jsonb_array_length(tipos) <> 12 THEN
    RAISE EXCEPTION 'esquema do painel nao ganhou os 12 tipos de elemento: %', tipos;
  END IF;
END $$;
