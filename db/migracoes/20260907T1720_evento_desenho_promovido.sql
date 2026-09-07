-- 20260907T1720_evento_desenho_promovido: tipo de evento para "promover a camada" (item L2-01-k), em
-- arquivo NOVO porque 20260907T1655_anotacao_feicao.sql já tinha sido aplicado nesta base quando o evento
-- foi acrescentado (regra do BRIEF_WORKTREES.md: correção de migração já aplicada nunca edita o arquivo).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('mapa/desenho_promovido', 'camada de desenho do mapa promovida a camada hospedada (L2-01-k)')
ON CONFLICT (nome) DO NOTHING;
