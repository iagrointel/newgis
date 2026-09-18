-- Item L1-02-e ("Porta 2"): GET /api/imagens/conexao-s3 registra um evento do tipo `imagens/conexao-s3`
-- (quem pediu a credencial S3 só-leitura do balde do inquilino, e quando). `plat.evento.tipo` tem chave
-- estrangeira para `plat.evento_tipo`, então sem esta linha a rota inteira falhava com ForeignKeyViolation
-- e devolvia 500 em TODA chamada — defeito que o portão do item não via, porque só conferia por `grep` que
-- a rota existia no código. Achado em 18/09/2026 pelo primeiro teste escrito contra a rota.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/conexao-s3', 'credencial S3 somente-leitura do balde do inquilino entregue para ArcGIS Pro/GDAL (L1-02-e); o segredo NUNCA entra no evento, só o balde e o modo')
ON CONFLICT (nome) DO NOTHING;
