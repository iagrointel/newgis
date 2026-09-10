-- 20260907T1303_campo_evento: item L2-07-a-pwa-instalavel-cache. `app/campo/rotas.py::campo_sessao` chama
-- `registrar_evento(..., "campo/sessao", ...)` a cada token de campo emitido; sem a linha em
-- `plat.evento_tipo` a FK derruba a rota inteira em 500 (mesmo defeito da migração 048, agora prevenido
-- antes do adversário achar).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('campo/sessao', 'token de campo emitido (PWA de campo, escopo campo:usar, 30 dias; nunca o token em si)')
ON CONFLICT (nome) DO NOTHING;
