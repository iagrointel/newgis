-- 20260907T2225_upload_recusa_evento: vocabulário de evento do pipeline único de upload (item
-- L7-03-a-antivirus-upload). Toda recusa de conteúdo (tipo fora da lista da rota, bytes que não batem com o
-- declarado, zip-bomba, SVG inválido, antivírus) vira uma linha em plat.evento — a "trilha" do portão (L7-20) —
-- com classe, Content-Type declarado, tipo detectado, motivo e, quando é o antivírus, o nome da assinatura e o
-- sha256 do que foi recusado (a QUARENTENA é o registro: o conteúdo não é guardado). Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('arquivos/conteudo_recusado', 'upload recusado pelo pipeline único (tipo fora da rota, bytes, zip-bomba, SVG, tamanho)'),
  ('arquivos/quarentena', 'upload recusado pelo antivírus (clamd): sha256 e assinatura registrados, conteúdo descartado')
ON CONFLICT (nome) DO NOTHING;
