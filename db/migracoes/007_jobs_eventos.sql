-- 007_jobs_eventos (integração T2 com a identidade, ADR 0002 seção 9.4 / D14): vocabulário de eventos de domínio da
-- fila de jobs em plat.evento_tipo. Toda rota de escrita de /api/jobs e /api/agendas declara o evento em
-- tests/api/eventos_esperados.py e o registra por plat.evento_registrar (app/jobs/rotas.py). Idempotente.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('jobs/criar', 'job enfileirado pela API (criar, repetir ou rodar agora de uma agenda; propriedades.tipo)'),
  ('jobs/cancelar', 'cancelamento pedido pelo usuário (propriedades.resultado: cancelado|solicitado)'),
  ('agendas/criar', 'agenda criada (propriedades.tipo, cron, fuso)'),
  ('agendas/atualizar', 'agenda alterada (nome, tipo, parâmetros, cron, fuso ou expiração)'),
  ('agendas/apagar', 'agenda apagada'),
  ('agendas/pausar', 'agenda pausada pelo usuário'),
  ('agendas/retomar', 'agenda retomada pelo usuário (falhas seguidas zeradas)')
ON CONFLICT (nome) DO NOTHING;
