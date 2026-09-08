-- 20260906T1823_multiescala_apagar: tipos de evento para DELETE de conjunto/fator (item L3-19-multiescala).
--
-- A 20260906T1640 só previu os eventos de criação/execução; a limpeza de teste (cruzado_casos.py,
-- tests/api/multiescala) precisa apagar o conjunto/fator que criou, e `plat.evento_registrar` tem FK para
-- `plat.evento_tipo` — sem a linha, `DELETE /api/multiescala/conjuntos/{id}` cairia em 500 (mesma classe de
-- lacuna do L0-07-d, corrigida na 20260906T18.. daquele item). Correção em arquivo NOVO (a 20260906T1640 já
-- foi aplicada nesta base). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('multiescala/conjunto_apagar', 'área de estudo multiescala apagada (cascata: grades, células, execuções)'),
  ('multiescala/fator_apagar', 'fator multiescala apagado (cascata: amostras, blocos, linhas de execução)')
ON CONFLICT (nome) DO NOTHING;
