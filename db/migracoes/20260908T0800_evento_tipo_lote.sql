-- 20260908T0800: evento de domínio da edição em lote (item L2-03-f-edicao-em-lote-calculo-campo).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/lote', 'edição em lote aplicada ou enfileirada como job (calcular/atribuir/apagar/corrigir/copiar/mover; L2-03-f)')
ON CONFLICT (nome) DO NOTHING;
