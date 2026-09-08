-- item L2-16-a-sdk-python-geo: tipo de item `ferramenta_resultado` — o resultado de uma ferramenta
-- executada por job (ex.: `ferramentas.buffer` do SDK) vira item do catálogo com procedência.
-- O INSERT do item é feito pela própria tarefa do job (padrão de app/ingestao/carregar.py), direto
-- em plat.item, com os campos que o esquema deste tipo valida.

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
  ('ferramenta_resultado', 'ferramenta', 'Resultado de ferramenta',
   'resultado de uma ferramenta executada por job (ferramenta, parâmetros, resultado e job de origem)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["ferramenta","parametros","resultado"],
     "properties":{
       "ferramenta":{"type":"string","maxLength":120},
       "parametros":{"type":"object"},
       "resultado":{"type":"object"},
       "job_id":{"type":"string","format":"uuid"},
       "procedencia":{"type":"object"}}}'::jsonb,
   1, '', '', '{}', false, 'L2-16')
ON CONFLICT (nome) DO NOTHING;
