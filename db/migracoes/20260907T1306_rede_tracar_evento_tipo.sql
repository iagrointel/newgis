-- item L4-02-a-conectado-e-subrede: registra o tipo de evento do traçado (conectado/subrede) na
-- tabela de catálogo `plat.evento_tipo` — sem esta linha, `registrar_evento(..., "redes/tracar", ...)`
-- em rotas_topologia.py falha com ForeignKeyViolation (achado ao medir este item).

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/tracar', 'traçado conectado ou subrede executado sobre a topologia derivada (tipo, contagem, duração)')
ON CONFLICT (nome) DO NOTHING;
