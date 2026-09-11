-- 20260910T2210_backup_restore_drill: item L0-06-backup-status — ensaio de restauração. Restaura o último
-- dump do inquilino num schema TEMPORÁRIO da MESMA base (`plat_ensaio_<hex>`; o Postgres é compartilhado
-- com sistemas de cliente — sem banco novo, sem reinício), confere COUNT(*) de cada tabela contra a
-- produção e sempre derruba o schema temporário. Porta /home/dev/fgr/sig/pipeline/restore_test.sh (que usa
-- um BANCO separado, opção fechada aqui — ver app/backup/__init__.py). `app/backup/tarefas.py::
-- backup_ensaio_restauracao` é quem grava. Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.backup_drill (
  id                  bigserial PRIMARY KEY,
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  backup_id           bigint REFERENCES plat.backup(id) ON DELETE SET NULL,
  job_id              uuid,
  esquema             text NOT NULL,
  schema_ensaio       text,
  tabelas             int NOT NULL DEFAULT 0 CHECK (tabelas >= 0),
  linhas              bigint NOT NULL DEFAULT 0 CHECK (linhas >= 0),
  divergencias        jsonb NOT NULL DEFAULT '[]'::jsonb,
  posteriores         jsonb NOT NULL DEFAULT '[]'::jsonb,
  objetos_conferidos  int NOT NULL DEFAULT 0 CHECK (objetos_conferidos >= 0),
  ok                  boolean NOT NULL,
  mensagem            text,
  duracao_drill_s     numeric NOT NULL CHECK (duracao_drill_s >= 0),
  origem              text NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual', 'periodico')),
  criado_em           timestamptz NOT NULL DEFAULT now()
);
-- (fusão wt/uniao x wt/lancamento, 11/09) plat.backup_drill já existia (migração 20260907T2155, desenho
-- global do L0-06-c-restore-drill, já reconciliado ali com um 3º desenho anterior); o CREATE acima foi
-- ignorado por já existir. União aditiva das colunas que só este desenho declara:
ALTER TABLE plat.backup_drill ADD COLUMN IF NOT EXISTS job_id uuid;
ALTER TABLE plat.backup_drill ADD COLUMN IF NOT EXISTS schema_ensaio text;

CREATE INDEX IF NOT EXISTS ix_backup_drill_tenant_criado ON plat.backup_drill (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_backup_drill_backup ON plat.backup_drill (backup_id);

ALTER TABLE plat.backup_drill ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_backup_drill ON plat.backup_drill;
CREATE POLICY p_backup_drill ON plat.backup_drill FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

REVOKE ALL ON plat.backup_drill FROM PUBLIC;
GRANT SELECT, INSERT ON plat.backup_drill TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.backup_drill_id_seq TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('backup/ensaio_restauracao', 'ensaio de restauração do backup do inquilino (L0-06): veredito ok/reprovado, contagens')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- agenda periódica, PAUSADA (pedido do turno)
-- `app/backup/periodicos.py` declara os dois periódicos para `sincronizar_periodicos` (app/jobs/agenda.py)
-- sincronizar a cada partida do worker — mas aquela função faz UPSERT sem tocar `ativa`, e a tabela nasce
-- com `ativa DEFAULT true` (004_jobs.sql): sem semear a linha aqui primeiro, a PRIMEIRA sincronização
-- ligaria os dois periódicos sozinha, contra o pedido explícito do turno ("sem ligar cron nenhum: só a
-- agenda no banco, pausada, para o dono decidir"). Semeando com `ativa = false` ANTES, a sincronização
-- posterior faz UPDATE só de tipo/parametros/cron/fuso — `ativa` fica como está.
INSERT INTO plat.agenda (tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, ativa)
SELECT t.id, NULL, v.nome, v.tipo, v.parametros::jsonb, v.cron, 'America/Sao_Paulo', false
FROM plat.tenant t,
     (VALUES
       ('backup lógico diário', 'backup.executar', '{"origem":"periodico"}', '0 3 * * *'),
       ('ensaio de restauração semanal', 'backup.ensaio_restauracao', '{"origem":"periodico"}', '30 4 * * 0')
     ) AS v(nome, tipo, parametros, cron)
WHERE t.slug = 'plataforma'
ON CONFLICT (tenant_id, nome) DO NOTHING;
