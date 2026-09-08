-- 20260907T1845_pacote_de_mapa (item L2-01-l-exportacao-do-mapa): os dois eventos do PACOTE DE MAPA.
--
-- `plat.evento` tem chave estrangeira para `plat.evento_tipo`: um tipo de evento não declarado faz a rota
-- inteira falhar com violação de chave estrangeira (medido nesta trilha em 07/09/2026, ao exportar o
-- primeiro pacote). Por isso o tipo entra por migração, e não por cadastro em tempo de execução.
--
-- Nada mais é preciso para o item: a exportação do pacote reaproveita `plat.exportacao` (formato
-- `pacote`, item de origem do tipo `mapa`), e a reimportação cria itens comuns de catálogo — nenhuma
-- tabela nova, nenhuma coluna nova.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('mapas/exportar_pacote', 'pacote do mapa pedido: documento, estilos e dados das camadas citadas (item L2-01-l)'),
  ('mapas/importar_pacote', 'pacote de mapa reimportado: camadas e documento recriados neste inquilino')
ON CONFLICT (nome) DO NOTHING;
