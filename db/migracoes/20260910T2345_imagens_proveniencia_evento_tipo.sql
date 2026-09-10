-- item L1-01-j (proveniência verificável da imagem): duas rotas novas em app/imagens/rotas_imagens.py
-- registram evento com tipo próprio — sem a linha em plat.evento_tipo a rota dá 500 (evento_tipo_fkey),
-- mesmo defeito já corrigido uma vez em 20260910T0245_imagens_evento_tipo.sql. Idempotente.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('imagens/conferir', 'item L1-01-j: POST /api/imagens/{item_id}/conferir (recalcula e compara sha256)'),
  ('imagens/preencher_proveniencia_lote',
   'item L1-01-j: POST /api/imagens/proveniencia/preencher-pendentes (preenchimento retroativo em lote)')
ON CONFLICT (nome) DO NOTHING;
