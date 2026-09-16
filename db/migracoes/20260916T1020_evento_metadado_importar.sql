-- 20260916T1020_evento_metadado_importar: item L0-09-c-xml-iso-validacao. `POST /api/itens/{id}/metadado.xml`
-- (a rota de importação, restaurada nesta mesma rodada em app/catalogo/rotas_itens.py — o modelo de entrada
-- MetadadoIsoEntrada existia em app/catalogo/modelos.py, mas nenhuma rota o usava e o analisador
-- app.catalogo.metadado.analisar nunca era chamado pela API) registra `itens/metadado_importar`, tipo de
-- evento que nunca tinha sido cadastrado. Sem a linha em plat.evento_tipo, plat.evento_registrar (gatilho de
-- FK) rejeitava a gravação com ForeignKeyViolation. Idempotente; sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('itens/metadado_importar', 'metadado ISO 19139 importado no item por POST /api/itens/{id}/metadado.xml')
ON CONFLICT (nome) DO NOTHING;
