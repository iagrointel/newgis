-- Item L2-05-e (ferramentas raster): o resultado de uma ferramenta é um item `raster` e precisa carregar a
-- MESMA proveniência que o resultado vetorial já carrega (`camada_vetorial.dados.procedencia`, migração 011).
-- O esquema do tipo `raster` é fechado (`additionalProperties: false`), então sem esta migração o item de
-- análise sairia sem dizer de que ferramenta, de que entrada e com que parâmetros nasceu. Acrescenta só a
-- propriedade `procedencia` (objeto aberto), sem mexer em required nem em nenhuma outra propriedade.
-- Idempotente: reaplicar não muda nada além de reescrever a mesma propriedade.
UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,procedencia}',
                           '{"type":"object","additionalProperties":true}'::jsonb, true),
       esquema_versao = GREATEST(esquema_versao, 2)
 WHERE nome = 'raster'
   AND NOT (esquema -> 'properties' ? 'procedencia');
