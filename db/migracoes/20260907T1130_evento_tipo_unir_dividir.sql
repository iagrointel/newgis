-- 20260907T1130: eventos de domínio de união/divisão de feição (item L2-03-edicao).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/unir', 'duas ou mais feições substituídas por uma feição unida (L2-03-edicao)'),
  ('camadas/dividir', 'uma feição de linha substituída por duas (L2-03-edicao)')
ON CONFLICT (nome) DO NOTHING;
