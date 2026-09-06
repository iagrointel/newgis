-- Item L6-02-o-importacao-exportacao-formatos: `plat.evento_tipo` é vocabulário fechado (FK de `plat.evento`,
-- ver 029_ingestao_vetor.sql) — os jobs/rotas novos de exportação (`app/ingestao/exportar.py`,
-- `app/ingestao/rotas_exportar.py`) precisam dos 4 tipos abaixo cadastrados antes de registrar o primeiro
-- evento, senão `plat.evento_registrar` estoura `ForeignKeyViolation` (medido nesta passagem). Idempotente.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/exportar_pedir', 'exportação de uma camada vetorial pedida (job ingestao.exportar_camada)'),
  ('camadas/exportar', 'exportação de uma camada vetorial concluída, objeto gravado'),
  ('org/exportar_pedir', 'exportação do inquilino inteiro pedida (job ingestao.exportar_inquilino, escrow L0-06)'),
  ('org/exportar', 'exportação do inquilino inteiro concluída, GeoPackage + manifesto gravados')
ON CONFLICT (nome) DO NOTHING;
