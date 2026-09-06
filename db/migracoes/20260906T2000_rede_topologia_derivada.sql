-- 20260906T2000_rede_topologia_derivada: TOPOLOGIA DERIVADA da rede de utilidades (item L4-01-b-topologia-derivada;
-- ADR 0020). Depende de 20260906T1553 (plat.rede_*) e 20260906T1815 (FK composta por inquilino).
--
-- Hipótese do item: as camadas de rede continuam camadas normais e editáveis; a TOPOLOGIA é um ÍNDICE DERIVADO,
-- reconstruído por "habilitar topologia" a partir delas — nunca a fonte da verdade. Nesta passagem a "camada de
-- rede" é um par de tabelas genéricas por rede, `plat.rede_feicao_ponto` (dispositivo) e `plat.rede_feicao_linha`
-- (trecho), cada feição presa a um `plat.rede_tipo` do pacote já importado (item L4-01-a). Unificar isso com o
-- catálogo geral de camadas (`camada_vetorial`, tabela dinâmica `d_<slug>.c_<uuid>`) é fronteira honesta desta
-- passagem — ver docs/rede/TOPOLOGIA.md seção "fronteira".
--
-- `plat.rede_topo_no` e `plat.rede_topo_aresta` guardam o resultado: um nó por vértice de conexão (onde trechos
-- se tocam) e por terminal de dispositivo (mesmo quando dois terminais do MESMO dispositivo caem no mesmo ponto
-- físico — ver `app/rede_utilidades/topologia.py`), uma aresta por trecho, com origem/destino, custo geodésico e
-- bitmask de fase. `plat.rede_topo_resumo` grava a contagem de cada rodada de "habilitar". Tudo dado do
-- INQUILINO (RLS), como as tabelas de 20260906T1553. Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- tolerância de coincidência é parâmetro DA REDE (cláusula 1 do portão), não da instalação inteira.
ALTER TABLE plat.rede ADD COLUMN IF NOT EXISTS tolerancia_m numeric NOT NULL DEFAULT 0.05
  CHECK (tolerancia_m > 0 AND tolerancia_m <= 10);

-- feição-dispositivo (grupo geometria='ponto'): um transformador, uma chave, um poste. `tipo_id` já carrega o
-- grupo (rede_tipo.grupo_id) e o terminal_config (rede_tipo.terminal_id) — não se duplica aqui.
CREATE TABLE IF NOT EXISTS plat.rede_feicao_ponto (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  tipo_id       uuid NOT NULL,
  geom          geometry(Point, 4326) NOT NULL,
  fase_bitmask  smallint CHECK (fase_bitmask IS NULL OR fase_bitmask BETWEEN 0 AND 7),
  atributos     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ponto_tenant ON plat.rede_feicao_ponto (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ponto_rede ON plat.rede_feicao_ponto (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ponto_tipo ON plat.rede_feicao_ponto (tipo_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_ponto_geom ON plat.rede_feicao_ponto USING gist (geom);
ALTER TABLE plat.rede_feicao_ponto ADD CONSTRAINT rede_feicao_ponto_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao_ponto ADD CONSTRAINT rede_feicao_ponto_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- feição-trecho (grupo geometria='linha'): trecho de MT/BT, ramal de ligação.
CREATE TABLE IF NOT EXISTS plat.rede_feicao_linha (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  tipo_id       uuid NOT NULL,
  geom          geometry(LineString, 4326) NOT NULL,
  fase_bitmask  smallint CHECK (fase_bitmask IS NULL OR fase_bitmask BETWEEN 0 AND 7),
  atributos     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_linha_tenant ON plat.rede_feicao_linha (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_linha_rede ON plat.rede_feicao_linha (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_linha_tipo ON plat.rede_feicao_linha (tipo_id);
CREATE INDEX IF NOT EXISTS ix_rede_feicao_linha_geom ON plat.rede_feicao_linha USING gist (geom);
ALTER TABLE plat.rede_feicao_linha ADD CONSTRAINT rede_feicao_linha_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_feicao_linha ADD CONSTRAINT rede_feicao_linha_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- nó de topologia: papel 'conexao' (vértice onde trechos se tocam, sem feição própria) ou 'terminal' (terminal
-- de um dispositivo — `origem_id`/`terminal_num` apontam a feição e QUAL dos N terminais declarados no pacote).
CREATE TABLE IF NOT EXISTS plat.rede_topo_no (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  papel         text NOT NULL CHECK (papel IN ('conexao', 'terminal')),
  tipo_id       uuid,
  origem_id     uuid,
  terminal_num  int CHECK (terminal_num IS NULL OR terminal_num BETWEEN 1 AND 8),
  geom          geometry(Point, 4326) NOT NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_topo_no_tenant ON plat.rede_topo_no (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_no_rede ON plat.rede_topo_no (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_no_geom ON plat.rede_topo_no USING gist (geom);
ALTER TABLE plat.rede_topo_no ADD CONSTRAINT rede_topo_no_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_no ADD CONSTRAINT rede_topo_no_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_no ADD CONSTRAINT rede_topo_no_tenant_origem_fkey
  FOREIGN KEY (tenant_id, origem_id) REFERENCES plat.rede_feicao_ponto (tenant_id, id) ON DELETE CASCADE;

-- aresta de topologia: uma por feição de trecho. `no_origem_id`/`no_destino_id` NULL = "aresta sem nó" (a feição
-- não entrou na construção — hoje só acontece com trecho degenerado, comprimento 0, ver topologia.py).
CREATE TABLE IF NOT EXISTS plat.rede_topo_aresta (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  grupo_id       uuid NOT NULL,
  tipo_id        uuid,
  origem_id      uuid NOT NULL,
  no_origem_id   uuid,
  no_destino_id  uuid,
  comprimento_m  double precision NOT NULL CHECK (comprimento_m >= 0),
  fase_bitmask   smallint,
  atributos      jsonb NOT NULL DEFAULT '{}'::jsonb,
  geom           geometry(LineString, 4326) NOT NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_tenant ON plat.rede_topo_aresta (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_rede ON plat.rede_topo_aresta (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_geom ON plat.rede_topo_aresta USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_no_origem ON plat.rede_topo_aresta (no_origem_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_no_destino ON plat.rede_topo_aresta (no_destino_id);
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_grupo_fkey
  FOREIGN KEY (tenant_id, grupo_id) REFERENCES plat.rede_grupo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_origem_fkey
  FOREIGN KEY (tenant_id, origem_id) REFERENCES plat.rede_feicao_linha (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_no_origem_fkey
  FOREIGN KEY (tenant_id, no_origem_id) REFERENCES plat.rede_topo_no (tenant_id, id) ON DELETE SET NULL;
ALTER TABLE plat.rede_topo_aresta ADD CONSTRAINT rede_topo_aresta_tenant_no_destino_fkey
  FOREIGN KEY (tenant_id, no_destino_id) REFERENCES plat.rede_topo_no (tenant_id, id) ON DELETE SET NULL;

-- resumo: 1 linha viva por rede (a última rodada de "habilitar" substitui a anterior).
CREATE TABLE IF NOT EXISTS plat.rede_topo_resumo (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL UNIQUE,
  tolerancia_m     numeric NOT NULL,
  nos              int NOT NULL,
  arestas          int NOT NULL,
  nos_orfaos       int NOT NULL,
  arestas_sem_no   int NOT NULL,
  duracao_ms       int NOT NULL,
  construido_em    timestamptz NOT NULL DEFAULT now(),
  construido_por   int REFERENCES plat.usuario(id)
);
CREATE INDEX IF NOT EXISTS ix_rede_topo_resumo_tenant ON plat.rede_topo_resumo (tenant_id);
ALTER TABLE plat.rede_topo_resumo ADD CONSTRAINT rede_topo_resumo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260906T1553. Leitura pelo inquilino; escrita exige `rede.editar` (avaliado na aplicação).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_feicao_ponto', 'rede_feicao_linha', 'rede_topo_no', 'rede_topo_aresta',
                           'rede_topo_resumo'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/feicao_criar', 'feição de rede criada (ponto ou linha; tipo, rede)'),
  ('redes/topologia_habilitar', 'topologia da rede (re)construída (tolerância, contagens, duração)')
ON CONFLICT (nome) DO NOTHING;
