-- A rota POST /api/imagens/ingestoes (item L1-01-i) registra o evento "imagens/ingestar", que nunca
-- foi cadastrado em plat.evento_tipo: qualquer POST pela rota terminava em 500 por violação da
-- evento_tipo_fkey (exposto pelo teste de formatos de entrada, item L1-01-f: o job enfileirado fica
-- pendente, mas o evento de auditoria é obrigatório na mesma transação da rota).
INSERT INTO plat.evento_tipo(nome, descricao)
VALUES ('imagens/ingestar',
        'ingestão de imagem enfileirada: envio de item de arquivo raster ao job imagens.ingestar')
ON CONFLICT (nome) DO NOTHING;
