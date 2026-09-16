-- `plat.tipo_item.esquema` de 'raster' perdeu duas propriedades que duas migrações anteriores já tinham
-- acrescentado: `procedencia` (20260906T1544c24_procedencia_item.sql, esquema_versao 1->2) e
-- `guardar_original` (20260908T1911_raster_ciclo_vida.sql, sem bump de versão). A causa raiz é
-- `20260910T1500_item_servico_estavel.sql`: ela faz `INSERT ... ON CONFLICT (nome) DO UPDATE` com um
-- esquema NOVO cravado no arquivo (só acrescenta `servico`) e decide qual lado vence só por
-- `esquema_versao > EXCLUDED.esquema_versao` — em EMPATE (2 == 2, que é exatamente o caso desta tabela
-- depois das duas migrações acima) o CASE cai no ELSE e usa o esquema CRAVADO, apagando `procedencia` e
-- `guardar_original` que a UPDATE aditiva anterior tinha posto lá. Medido 16/09/2026: `test_ciclo_vida.py`
-- e `test_formatos_entrada.py` (tests/api/imagens) mandam `guardar_original` em `dados` e levam
-- `422 dados fora do esquema do tipo raster` (`additionalProperties: false` recusa a chave).
--
-- Conserto pela regra da casa desta classe (mesma de 20260911T1320/1325_raster_item_*_uniao.sql): UNIÃO
-- aditiva, nunca reescrever o esquema inteiro — `20260910T1500` não é tocada (arquivo aplicado é
-- imutável) e o `ON CONFLICT` dela continua com o bug para quem migrar do zero num futuro distante,
-- mas esta migração roda DEPOIS na cadeia e devolve as duas propriedades sem depender de reordenar nada.
UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,procedencia}',
                           '{"type":["object","null"],"additionalProperties":true}'::jsonb, true),
       esquema_versao = GREATEST(esquema_versao, 3)
 WHERE nome = 'raster'
   AND NOT (esquema -> 'properties' ? 'procedencia');

UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,guardar_original}', '{"type":"boolean"}'::jsonb, true),
       esquema_versao = GREATEST(esquema_versao, 3)
 WHERE nome = 'raster'
   AND NOT (esquema -> 'properties' ? 'guardar_original');
