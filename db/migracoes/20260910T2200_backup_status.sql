-- 20260910T2200_backup_status: item L0-06-backup-status (linha L0 fundação) — backup lógico POR INQUILINO,
-- portado de /home/dev/fgr/sig/pipeline/backup.sh (pg_dump -Fc do schema + sha256 + tabela de registro).
-- Diferença do original por causa do multi-inquilino do PLAT: aqui não há bucket global 'plat-backup' — o
-- dump sobe ao bucket do PRÓPRIO inquilino no Garage (app/objetos.py, mesmo caminho que app/imagens usa
-- para o COG). `app/backup/tarefas.py::backup_executar` é quem grava. Idempotente. Sem BEGIN/COMMIT.
-- Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.backup (
  id             bigserial PRIMARY KEY,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  job_id         uuid,
  esquema        text NOT NULL,
  chave          text NOT NULL,
  sha256         text NOT NULL,
  bytes          bigint NOT NULL CHECK (bytes >= 0),
  tabelas        int NOT NULL CHECK (tabelas >= 0),
  tempo_dump_s   numeric NOT NULL CHECK (tempo_dump_s >= 0),
  origem         text NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual', 'periodico')),
  criado_por     int REFERENCES plat.usuario(id),
  criado_em      timestamptz NOT NULL DEFAULT now()
);
-- (fusão wt/uniao x wt/lancamento, 11/09) plat.backup já existia (migração 20260906T2125, desenho global
-- do L0-06-a-dump-logico); o CREATE acima foi ignorado por já existir. A tabela passa a ser a união dos
-- dois desenhos, aditivamente — sem NOT NULL/CHECK/REFERENCES aqui (dado antigo pode não passar):
ALTER TABLE plat.backup ADD COLUMN IF NOT EXISTS job_id uuid;
ALTER TABLE plat.backup ADD COLUMN IF NOT EXISTS chave text;
ALTER TABLE plat.backup ADD COLUMN IF NOT EXISTS criado_por int;

CREATE INDEX IF NOT EXISTS ix_backup_tenant_criado ON plat.backup (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_backup_job ON plat.backup (job_id);

ALTER TABLE plat.backup ENABLE ROW LEVEL SECURITY;

-- FOR ALL (não só SELECT): é o próprio job do inquilino, sob RLS normal, que faz o INSERT — mesmo desenho
-- de p_agol_publicacao (20260910T2015_agol.sql), sem terceiro inquilino a proteger de outro jeito.
DROP POLICY IF EXISTS p_backup ON plat.backup;
CREATE POLICY p_backup ON plat.backup FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

REVOKE ALL ON plat.backup FROM PUBLIC;
GRANT SELECT, INSERT ON plat.backup TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.backup_id_seq TO plat_app;

-- ---------------------------------------------------------------- eventos novos
-- sem isto a rota/job dá 500 (evento.tipo referencia plat.evento_tipo.nome) — defeito real medido nesta
-- trilha antes desta migração existir (achado registrado no item L0-06-backup-status).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('backup/executar', 'backup lógico do inquilino (L0-06): dump do schema, sha256 e cópia no bucket do inquilino'),
  ('backup/falha', 'backup ou ensaio de restauração falhou (L0-06): motivo e detalhe, nunca silêncio')
ON CONFLICT (nome) DO NOTHING;
