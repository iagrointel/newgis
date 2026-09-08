-- Item L4-05-c-pandapower-e-matpower: registra `redes/importar_matpower` no catálogo `plat.evento_tipo`.
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
--
-- A rota POST /api/rede/{rede_id}/matpower chama `registrar_evento(..., "redes/importar_matpower", ...)`
-- e a chave estrangeira do evento recusa qualquer nome fora deste catálogo — sem esta linha a rota grava
-- as barras e falha ao registrar o evento. Mesmo motivo da migração 20260907T2210.
-- Idempotente. Sem BEGIN/COMMIT.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/importar_matpower', 'caso MATPOWER importado para o grafo da rede (barras e ramos, sem geometria)')
ON CONFLICT (nome) DO NOTHING;
