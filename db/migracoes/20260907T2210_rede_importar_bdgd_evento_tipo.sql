-- Item L4-01-c-importador-bdgd: registra `redes/importar_bdgd` no catálogo `plat.evento_tipo`.
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
--
-- A rota POST /api/rede/{rede_id}/importar-bdgd chama `registrar_evento(..., "redes/importar_bdgd", ...)`
-- e a chave estrangeira do evento recusa qualquer nome fora deste catálogo — sem esta linha a rota grava o
-- job e falha ao registrar o evento. Mesmo motivo da migração 20260907T1306 para `redes/tracar`.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/importar_bdgd', 'importação BDGD enfileirada como job (rede, caminho do pacote, id do job)')
ON CONFLICT (nome) DO NOTHING;
