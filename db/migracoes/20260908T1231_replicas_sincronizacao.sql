-- 20260908T1231_replicas_sincronizacao: item L2-13-b-replicas-sincronizacao. Réplica para trabalho
-- desconectado (base do L2-07-c PWA de campo, do L2-04-k e do QField): recorte declarado de camadas ->
-- GeoPackage -> edição fora de rede -> sincronização com detecção de conflito por versão.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 20260907T1025_historico_feicao.sql
--
-- Rastreio: NÃO se cria tabela de rastreio. `plat.feicao_historico` (20260907T1025, item L2-03-edicao) já
-- grava por gatilho AFTER toda escrita em `d_<slug>.c_<uuid16>`, inclusive o DELETE — que é justamente a
-- operação que a tabela de camada não consegue guardar sozinha. O `id bigserial` dessa tabela é o relógio
-- lógico da réplica: "o que mudou desde a geração G" é `id > G` com o índice acrescentado aqui, sem varrer
-- a tabela de camada. É o rastreio (fid, versao, momento) que o L2-03-d prevê, já existente.
CREATE INDEX IF NOT EXISTS ix_feicao_historico_desde
  ON plat.feicao_historico (tenant_id, schema_dado, tabela_dado, id);

-- ---------------------------------------------------------------- plat.replica
CREATE TABLE IF NOT EXISTS plat.replica (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            int  NOT NULL REFERENCES plat.tenant(id),
  nome                 text NOT NULL CHECK (length(nome) BETWEEN 1 AND 200),
  dono_id              int  NOT NULL REFERENCES plat.usuario(id),
  dispositivo          text CHECK (dispositivo IS NULL OR length(dispositivo) <= 200),
  politica_conflito    text NOT NULL DEFAULT 'servidor_vence'
                       CHECK (politica_conflito IN ('servidor_vence','cliente_vence','pergunta')),
  extensao             geometry(Polygon, 4326),   -- recorte espacial do pacote; NULL = camada inteira
  com_anexos           boolean NOT NULL DEFAULT false,
  estado               text NOT NULL DEFAULT 'criando'
                       CHECK (estado IN ('criando','pronta','falhou')),
  geracao              int  NOT NULL DEFAULT 0,   -- avança 1 a cada sincronização aplicada (monotônica)
  job_id               uuid,
  pacote_chave         text,
  pacote_bytes         bigint,
  pacote_sha256        text,
  erro                 text,
  criada_em            timestamptz NOT NULL DEFAULT now(),
  expira_em            timestamptz NOT NULL,
  ultima_sincronizacao timestamptz
);
CREATE INDEX IF NOT EXISTS ix_replica_tenant ON plat.replica (tenant_id, criada_em DESC);
CREATE INDEX IF NOT EXISTS ix_replica_dono   ON plat.replica (tenant_id, dono_id, criada_em DESC);

ALTER TABLE plat.replica ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.replica FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_replica ON plat.replica;
CREATE POLICY p_replica ON plat.replica FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.replica TO plat_app;

-- ---------------------------------------------------------------- plat.replica_camada
-- `geracao_servidor` é o ponteiro no relógio lógico (plat.feicao_historico.id) até onde o cliente JÁ tem o
-- estado desta camada. Uma linha por camada da réplica: camadas diferentes avançam em ritmos diferentes.
CREATE TABLE IF NOT EXISTS plat.replica_camada (
  replica_id       uuid   NOT NULL REFERENCES plat.replica(id) ON DELETE CASCADE,
  camada_id        uuid   NOT NULL,
  tenant_id        int    NOT NULL REFERENCES plat.tenant(id),
  nome_gpkg        text   NOT NULL CHECK (nome_gpkg ~ '^[a-z][a-z0-9_]{0,58}$'),
  filtro           text   CHECK (filtro IS NULL OR length(filtro) <= 2000),
  geracao_servidor bigint NOT NULL DEFAULT 0,
  feicoes          int    NOT NULL DEFAULT 0,
  PRIMARY KEY (replica_id, camada_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_replica_camada_nome ON plat.replica_camada (replica_id, nome_gpkg);

ALTER TABLE plat.replica_camada ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.replica_camada FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_replica_camada ON plat.replica_camada;
CREATE POLICY p_replica_camada ON plat.replica_camada FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.replica_camada TO plat_app;

-- ---------------------------------------------------------------- plat.replica_sincronizacao
-- Livro de idempotência: a resposta INTEIRA de cada sincronização aplicada fica gravada sob a chave que o
-- cliente enviou. Repetir o mesmo lote (rede caiu depois de aplicar, antes de o cliente ler a resposta)
-- devolve a MESMA resposta e aplica ZERO — é a única defesa possível contra duplicar feição no servidor,
-- porque um `adicionar` não tem versão anterior com que discordar.
CREATE TABLE IF NOT EXISTS plat.replica_sincronizacao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int  NOT NULL REFERENCES plat.tenant(id),
  replica_id     uuid NOT NULL REFERENCES plat.replica(id) ON DELETE CASCADE,
  idempotencia   text NOT NULL CHECK (length(idempotencia) BETWEEN 8 AND 200),
  geracao_antes  int  NOT NULL,
  geracao_depois int  NOT NULL,
  resposta       jsonb NOT NULL,
  criada_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (replica_id, idempotencia)
);
CREATE INDEX IF NOT EXISTS ix_replica_sincronizacao ON plat.replica_sincronizacao (tenant_id, replica_id, criada_em DESC);

ALTER TABLE plat.replica_sincronizacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.replica_sincronizacao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_replica_sincronizacao ON plat.replica_sincronizacao;
CREATE POLICY p_replica_sincronizacao ON plat.replica_sincronizacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.replica_sincronizacao TO plat_app;

-- ---------------------------------------------------------------- eventos de domínio
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('replicas/criar', 'réplica de trabalho desconectado registrada e pacote GeoPackage enfileirado (L2-13-b)'),
  ('replicas/sincronizar', 'lote de sincronização de réplica aplicado (sobe do cliente, baixa do servidor; L2-13-b)'),
  ('replicas/apagar', 'réplica apagada pelo dono ou por administrador (L2-13-b)')
ON CONFLICT (nome) DO NOTHING;
