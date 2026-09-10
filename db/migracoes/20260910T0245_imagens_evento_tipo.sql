-- L1-02 (serviço de imagens): tipos de evento que app/imagens registra e que nenhuma migração semeava —
-- POST /api/imagens/ingestoes caía em evento_tipo_fkey (500). Idempotente.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/ingestar', 'serviço de imagens (L1-02): imagens/ingestar')
ON CONFLICT (nome) DO NOTHING;
