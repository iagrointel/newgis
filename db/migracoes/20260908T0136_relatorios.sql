-- 20260908T0142_relatorios: item L0-07-e-relatorios (relatórios do admin do inquilino como job, CSV baixável,
-- agendáveis com entrega por e-mail; painel Atividade). Só vocabulário de eventos: o dado dos relatórios já
-- existe (plat.usuario, plat.item, plat.grupo, plat.evento, plat.log_acesso, plat.arquivo, plat.job) e o CSV vai
-- para o armazenamento de objetos (classe `relatorio`, plat.arquivo da 022) como a exportação do catálogo.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('relatorios/gerar', 'relatório pedido pelo admin do inquilino (propriedades: tipo, janela, e-mail; alvo = job)'),
  ('relatorios/agendar', 'relatório agendado (propriedades: tipo, periodicidade, cron; alvo = agenda)')
ON CONFLICT (nome) DO NOTHING;
