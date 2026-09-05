-- 015_privilegio_jobs_ver (T2, correção 3 do L0-05, achado do testador): o perfil `visualizador` recebia 403 em
-- /api/jobs, /api/jobs/resumo e /api/jobs/tipos porque TODA rota da fila exigia `jobs.executar`, que o
-- visualizador não tem (ADR 0002 seção 3.2). A tela /tarefas ficava em "…" com 4 erros de console — P1 reprovado
-- para um perfil legítimo. O ADR 0002 dá ao visualizador a LEITURA do que é do inquilino dele (membros.ver,
-- grupos.ver_inquilino, conteudo.ver_inquilino); faltava a linha equivalente para a fila.
-- Correção: privilégio novo `jobs.ver` (não administrativo) nos quatro perfis; as rotas de LEITURA da fila passam
-- a exigir `jobs.ver` e as de EXECUÇÃO (criar, cancelar, repetir, agendas) seguem em `jobs.executar`. O filtro de
-- dono do ADR 0003 seção 9 não muda: quem não tem `jobs.gerir_todos` continua vendo só os próprios jobs, logo o
-- visualizador, que não cria job, lê uma lista vazia — sem 403 e sem erro de console.
-- O vocabulário passa de 46 para 47 privilégios (espelho em app/auth/privilegios.py, conferido pelo teste
-- tests/api/test_privilegios_declarados.py). Idempotente; sem BEGIN/COMMIT.

INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('jobs.ver', 'jobs', 'ver a lista, o detalhe, o log e os tipos de job do inquilino (leitura)', false)
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao,
                                 administrativo = EXCLUDED.administrativo;

-- a descrição de jobs.executar passa a dizer o que sobrou nele (a leitura saiu para jobs.ver)
UPDATE plat.privilegio SET descricao = 'criar, cancelar e repetir os próprios jobs, e gerir agendas'
 WHERE nome = 'jobs.executar';

INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('visualizador', 'jobs.ver'),
  ('campo',        'jobs.ver'),
  ('editor',       'jobs.ver'),
  ('admin',        'jobs.ver')
ON CONFLICT (perfil, privilegio) DO NOTHING;

-- papéis personalizados existentes que já podiam executar passam a poder ver (senão um papel que só tinha
-- jobs.executar perderia a leitura ao mudar o requisito das rotas de leitura)
INSERT INTO plat.papel_privilegio(papel_id, privilegio)
SELECT papel_id, 'jobs.ver' FROM plat.papel_privilegio WHERE privilegio = 'jobs.executar'
ON CONFLICT DO NOTHING;
