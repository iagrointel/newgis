-- 20260908T1450_corredor_evento: tipos de evento do motor de traçado linear (item L3-10-corredor-custo-minimo).
--
-- O traçado NÃO cria tabela: ele lê a grade e as notas de uma execução do motor multicritério
-- (`plat.escala_resultado`) e devolve a linha, o corredor e o manifesto na resposta. O que fica gravado é o
-- EVENTO, com os parâmetros declarados (custo máximo, origem do veto, vizinhança, epsilon) e as medidas do
-- traçado — é o rastro que permite repetir a corrida com o mesmo resultado. Guardar a geometria seria o item
-- de resultado-como-camada, que é outro.
-- Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('multiescala/corredor', 'traçado de custo mínimo entre dois pontos sobre as notas de uma execução do motor multicritério')
ON CONFLICT (nome) DO NOTHING;
