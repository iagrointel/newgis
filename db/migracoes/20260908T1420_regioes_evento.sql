-- 20260908T1420_regioes_evento: evento de localizar regiões (item L3-05-localizar-regioes, rota
-- POST /api/multiescala/execucoes/{id}/regioes). A rota não muda a execução — é uma PERGUNTA sobre ela —, mas o
-- pedido fica registrado com os parâmetros que o usuário escolheu (N, forma, método, compromisso, área total),
-- que é o que explica a resposta depois. Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('multiescala/regioes', 'regiões localizadas sobre a favorabilidade de uma execução (N, forma, método, área)')
ON CONFLICT (nome) DO NOTHING;
