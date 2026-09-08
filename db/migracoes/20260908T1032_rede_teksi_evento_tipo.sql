-- item L4-05-e-gas-e-esgoto: tipo de evento da importação de GeoPackage no esquema TEKSI (rede de esgoto).
-- Sem esta linha, `registrar_evento(..., "redes/teksi_importar", ...)` em rotas_gas_esgoto.py falha com
-- ForeignKeyViolation contra `plat.evento_tipo` (mesma armadilha do item L4-02-a).

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/teksi_importar',
   'importação de GeoPackage no esquema TEKSI para as feições da rede de esgoto (contagens, sha256, avisos)')
ON CONFLICT (nome) DO NOTHING;
