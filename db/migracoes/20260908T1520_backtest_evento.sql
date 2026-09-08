-- 20260908T1520_backtest_evento: evento do backtest contra decisão real (item L3-09-backtest-decisao-real,
-- rota POST /api/multiescala/execucoes/{id}/backtest). A rota não muda a execução; o registro guarda o que
-- explica a resposta depois (nº de escolhas, quantas caíram fora da grade, AUC, permutações, anacronismo).
-- Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('multiescala/backtest', 'backtest de uma execução contra escolhas reais (escolhas, fora, AUC, permutações)')
ON CONFLICT (nome) DO NOTHING;
