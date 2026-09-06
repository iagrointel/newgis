-- 20260906T2126_backup_status (item L0-06-backup-status; ADR 20260906T2126-backup-status):
-- quatro tabelas novas da fundação de continuidade do produto.
--
--   plat.backup          — registro de cada arquivo de dump lógico (scripts/backup/backup_diario.sh):
--                          um por escopo (a plataforma inteira = schema plat; um por inquilino = schema
--                          d_<slug>), com sha256 e tamanho para a conferência da página /status e do drill.
--   plat.backup_drill    — registro de cada ensaio de restauração (scripts/backup/restore_drill.sh):
--                          contagens conferidas e divergências; a refutação do item lê esta tabela.
--   plat.status_amostra  — sonda minuto a minuto dos serviços (periódico backup.status_amostrar,
--                          app/backup/tarefas.py): é o que dá uptime de verdade à página /status,
--                          não "estado agora". Sem tenant_id: o serviço é da instalação, não do inquilino.
--   plat.exportacao      — uma linha por "exportar meu inquilino" (botão em /admin/backup): a rota cria,
--                          o job backup.exportar_inquilino preenche arquivo/bytes/sha256 ao concluir.
--
-- RLS: toda tabela com tenant_id tem RLS + política (portão P6, test_migracoes.py). As duas sem tenant_id
-- (backup_drill, status_amostra) seguem o padrão de plat.versao_migracao: GRANT direto, leitura pela API.
-- A escrita em plat.backup/plat.backup_drill é SÓ do postgres (scripts em shell, dono das tabelas):
-- plat_app não recebe INSERT/UPDATE nelas — a API só lê. Idempotente; sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.backup (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  escopo        text NOT NULL,
  tenant_id     int REFERENCES plat.tenant(id),
  schema_nome   text NOT NULL,
  arquivo       text NOT NULL,
  bytes         bigint NOT NULL CHECK (bytes >= 0),
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  estado        text NOT NULL CHECK (estado IN ('concluido', 'falhou')),
  erro          text,
  iniciado_em   timestamptz NOT NULL,
  concluido_em  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_backup_escopo_tenant CHECK (
    (escopo = 'plataforma' AND tenant_id IS NULL) OR (escopo = 'inquilino' AND tenant_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_backup_tenant_em ON plat.backup (tenant_id, concluido_em DESC);
CREATE INDEX IF NOT EXISTS ix_backup_em ON plat.backup (concluido_em DESC);

ALTER TABLE plat.backup ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_backup_ler ON plat.backup;
-- o inquilino lê só as próprias linhas (a página /admin/backup); as de escopo plataforma (tenant_id NULL)
-- não aparecem para nenhum inquilino — o resumo público sai pela função plat.backup_resumo_publico() abaixo
CREATE POLICY p_backup_ler ON plat.backup FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
GRANT SELECT ON plat.backup TO plat_app;

CREATE TABLE IF NOT EXISTS plat.backup_drill (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  backup_em        timestamptz NOT NULL,           -- concluido_em do lote de dumps ensaiado
  estado           text NOT NULL CHECK (estado IN ('concluido', 'divergente', 'falhou')),
  tabelas          int NOT NULL DEFAULT 0,          -- tabelas conferidas (todas as dos schemas ensaiados)
  divergencias     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{schema, tabela, producao, restaurado}]
  erro             text,
  duracao_ms       int,
  criado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_backup_drill_em ON plat.backup_drill (criado_em DESC);
GRANT SELECT ON plat.backup_drill TO plat_app;

CREATE TABLE IF NOT EXISTS plat.status_amostra (
  id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  servico  text NOT NULL,
  estado   text NOT NULL CHECK (estado IN ('ok', 'erro', 'ausente')),
  em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_status_amostra_servico_em ON plat.status_amostra (servico, em DESC);
GRANT SELECT, INSERT, DELETE ON plat.status_amostra TO plat_app;

CREATE TABLE IF NOT EXISTS plat.exportacao (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  job_id       uuid,                                -- job backup.exportar_inquilino que produz o arquivo
  arquivo      text,                                -- caminho absoluto do .gpkg (NULL até concluir)
  bytes        bigint CHECK (bytes IS NULL OR bytes >= 0),
  sha256       text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  estado       text NOT NULL DEFAULT 'processando' CHECK (estado IN ('processando', 'concluido', 'falhou')),
  erro         text,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  concluido_em timestamptz
);
CREATE INDEX IF NOT EXISTS ix_exportacao_tenant_em ON plat.exportacao (tenant_id, criado_em DESC);

ALTER TABLE plat.exportacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_exportacao_ler ON plat.exportacao;
CREATE POLICY p_exportacao_ler ON plat.exportacao FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_exportacao_inserir ON plat.exportacao;
CREATE POLICY p_exportacao_inserir ON plat.exportacao FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_exportacao_alterar ON plat.exportacao;
-- o filho do job roda como plat_app dentro do inquilino do job (app/jobs/contexto_job.py): o UPDATE de
-- conclusão/falha passa pela MESMA política de tenant, sem função extra nem papel de worker
CREATE POLICY p_exportacao_alterar ON plat.exportacao FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE ON plat.exportacao TO plat_app;

-- ---------------------------------------------------------------- resumo público para /status
-- A página /status não tem sessão (pública interna), logo nenhum contexto de inquilino: sob RLS ela não
-- leria nada de plat.backup. O resumo que ela mostra é agregado e NÃO nomeia inquilino, caminho nem schema
-- (superfície mínima: quando foi o último lote, se concluiu, quantos arquivos) — por isso SECURITY DEFINER
-- com EXECUTE só para plat_app, mesmo padrão de plat.manutencao_analyze (026).
CREATE OR REPLACE FUNCTION plat.backup_resumo_publico()
RETURNS TABLE(ultimo_em timestamptz, estado text, arquivos int, bytes bigint)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.concluido_em, b.estado, x.arquivos, x.bytes
  FROM plat.backup b
  JOIN LATERAL (
    SELECT count(*)::int AS arquivos, sum(b2.bytes)::bigint AS bytes
    FROM plat.backup b2 WHERE b2.iniciado_em = b.iniciado_em
  ) x ON true
  ORDER BY b.concluido_em DESC LIMIT 1
$$;
REVOKE EXECUTE ON FUNCTION plat.backup_resumo_publico() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.backup_resumo_publico() TO plat_app;

-- vocabulário de evento do item (append; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/exportacao_solicitada', 'exportação do inquilino em GeoPackage enfileirada (botão em /admin/backup)'),
  ('org/exportacao_baixada',    'arquivo GeoPackage da exportação do inquilino baixado')
ON CONFLICT (nome) DO NOTHING;
