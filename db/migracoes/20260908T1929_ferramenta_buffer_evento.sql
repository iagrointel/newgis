-- item L2-16-a-sdk-python-geo: a tarefa do job `ferramentas.buffer` registra o evento de domínio
-- `ferramentas/buffer` quando o resultado vira item do catálogo. O tipo de evento precisa existir em
-- plat.evento_tipo (mesma regra das rotas: test_eventos confere o vocabulário contra o banco).
-- Migração separada da de 1847 porque aquela já tinha sido aplicada nas trilhas (mudança de sha
-- obrigaria a recriar a base).

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('ferramentas/buffer', 'resultado do buffer gravado como item de ferramenta pelo job do SDK')
ON CONFLICT (nome) DO NOTHING;
