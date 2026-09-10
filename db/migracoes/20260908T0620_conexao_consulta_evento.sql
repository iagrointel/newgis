-- 20260908T0620_conexao_consulta_evento: evento da consulta SQL do cliente no banco externo (item
-- L6-02-j-bancos-externos, rota POST /api/conexoes/{id}/consulta). Registra tabelas lidas, nº de linhas e
-- tempo — nunca o texto da consulta nem o dado devolvido. Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/consultar', 'consulta SQL só-leitura do cliente executada no banco externo (tabelas, linhas, tempo)')
ON CONFLICT (nome) DO NOTHING;
