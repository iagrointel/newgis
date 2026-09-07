-- item L2-05-a-catalogo-ferramentas-gpserver: proveniência de ferramenta no catálogo.
-- relação `derivado_de` (item produzido por ferramenta a partir de outro; L0-03-i) e evento de execução.
-- Idempotente. Aplicada por db/migrar.sh (produção) ou laco/trilha_ambiente.sh (base por trilha).
INSERT INTO plat.relacao_tipo(nome, descricao, origem_familias, destino_familias, arrasta_dono, apaga_junto) VALUES
  ('derivado_de', 'item produzido por ferramenta de análise a partir de outro (proveniência, L2-05-a)',
   '{camada,raster,arquivo,documento}', '{camada,raster,arquivo}', false, false)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('analises/executar', 'ferramenta de análise executada; item de resultado publicado com proveniência (L2-05-a)')
ON CONFLICT (nome) DO NOTHING;
