-- 20260907T1629_rede_epanet_importacao: importação/exportação EPANET .inp da rede de água (item
-- L4-05-d-epanet-inp). Depende de 20260906T1553 (plat.rede_*) e 20260906T2000 (feições + topologia derivada).
--
-- `plat.rede_importacao_epanet` é a fila de trabalho do job `rede.epanet_importar` (app/jobs/tipos.py):
-- guarda o arquivo .inp CRU (bytea; teto de 20 MiB, bem acima do maior arquivo real medido nesta casa —
-- 2.089.315 bytes, a rede de agua real usada nos testes) até o job ler e apagar (`arquivo_bytes = NULL` depois de processar,
-- nunca guardado para sempre: é fila de job, não arquivo do inquilino). `estado` segue o mesmo vocabulário
-- de `plat.importacao` (ingestão vetorial, ADR 0005): pendente -> executando -> concluida|falhou.
--
-- Duas colunas de geometria mudam nesta migração: `plat.rede_feicao_ponto.geom` e `plat.rede_feicao_linha.geom`
-- deixam de ser NOT NULL. Motivo (refutação do item): um nó do .inp sem linha em [COORDINATES] é um objeto de
-- rede REAL (tem ID, atributos, participa da topologia lógica por Node1/Node2) que só não tem onde desenhar —
-- a alternativa de inventar um ponto (0,0) foi rejeitada explicitamente pelo portão do item. Os atributos
-- (`atributos->>'epanet_no_id'` etc.) continuam a fonte de verdade para exportação; a geometria é só a
-- projeção espacial, quando existe. `topologia.py` (`_carregar_feicoes`) ganha `AND geom IS NOT NULL` nas duas
-- consultas de candidato: uma feição sem geometria não pode ganhar coordenada de topologia, então fica de fora
-- do índice derivado (nunca um nó fantasma em (0,0) ali também) — ver ADR 20260907T1629.
ALTER TABLE plat.rede_feicao_ponto ALTER COLUMN geom DROP NOT NULL;
ALTER TABLE plat.rede_feicao_linha ALTER COLUMN geom DROP NOT NULL;

CREATE TABLE IF NOT EXISTS plat.rede_importacao_epanet (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            int NOT NULL REFERENCES plat.tenant(id),
  rede_id              uuid NOT NULL,
  estado               text NOT NULL DEFAULT 'pendente'
                         CHECK (estado IN ('pendente','executando','concluida','falhou')),
  nome_arquivo         text CHECK (nome_arquivo IS NULL OR length(nome_arquivo) <= 260),
  crs_epsg             int CHECK (crs_epsg IS NULL OR crs_epsg BETWEEN 1024 AND 999999),
  arquivo_bytes        bytea CHECK (arquivo_bytes IS NULL OR octet_length(arquivo_bytes) <= 20971520),
  arquivo_sha256       text NOT NULL,
  arquivo_bytes_tamanho int NOT NULL CHECK (arquivo_bytes_tamanho >= 0),
  job_id               uuid,
  contagens            jsonb,
  avisos               jsonb,
  erro                 text,
  criado_por           int NOT NULL REFERENCES plat.usuario(id),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_importacao_epanet_tenant ON plat.rede_importacao_epanet (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_importacao_epanet_rede ON plat.rede_importacao_epanet (rede_id);
ALTER TABLE plat.rede_importacao_epanet ADD CONSTRAINT rede_importacao_epanet_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

CREATE OR REPLACE FUNCTION plat.tg_rede_importacao_epanet_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS rede_importacao_epanet_atualizado_em ON plat.rede_importacao_epanet;
CREATE TRIGGER rede_importacao_epanet_atualizado_em BEFORE UPDATE ON plat.rede_importacao_epanet
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_importacao_epanet_atualizado_em();

ALTER TABLE plat.rede_importacao_epanet ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_importacao_epanet_ler ON plat.rede_importacao_epanet;
CREATE POLICY p_rede_importacao_epanet_ler ON plat.rede_importacao_epanet
  FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_rede_importacao_epanet_inserir ON plat.rede_importacao_epanet;
CREATE POLICY p_rede_importacao_epanet_inserir ON plat.rede_importacao_epanet
  FOR INSERT TO plat_app WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_rede_importacao_epanet_alterar ON plat.rede_importacao_epanet;
CREATE POLICY p_rede_importacao_epanet_alterar ON plat.rede_importacao_epanet
  FOR UPDATE TO plat_app USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_rede_importacao_epanet_apagar ON plat.rede_importacao_epanet;
CREATE POLICY p_rede_importacao_epanet_apagar ON plat.rede_importacao_epanet
  FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.rede_importacao_epanet TO plat_app;

-- PATTERNS e CURVES do .inp não têm grupo/tipo no pacote agua-epanet (não são "ativo" — são a curva/série que
-- um ativo REFERENCIA por ID, ex.: `bomba_curva`/`no_padrao_de_demanda`). Sem guardá-las em algum lugar da
-- rede, a exportação nunca reconstrói `[CURVES]`/`[PATTERNS]` (achado deste item, `test_wntr_simula_o_inp_
-- exportado`: sem a curva, o `.inp` exportado tem uma bomba citando uma curva que não existe e `wntr` recusa).
-- Duas tabelas pequenas, por rede, substituídas inteiras a cada importação (mesma regra do pacote de ativos).
CREATE TABLE IF NOT EXISTS plat.rede_epanet_curva (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  rede_id    uuid NOT NULL,
  curva_id   text NOT NULL CHECK (btrim(curva_id) <> '' AND length(curva_id) <= 63),
  pontos     jsonb NOT NULL CHECK (jsonb_typeof(pontos) = 'array'),
  UNIQUE (tenant_id, rede_id, curva_id)
);
ALTER TABLE plat.rede_epanet_curva ADD CONSTRAINT rede_epanet_curva_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_rede_epanet_curva_tenant ON plat.rede_epanet_curva (tenant_id);

CREATE TABLE IF NOT EXISTS plat.rede_epanet_padrao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  padrao_id      text NOT NULL CHECK (btrim(padrao_id) <> '' AND length(padrao_id) <= 63),
  multiplicadores jsonb NOT NULL CHECK (jsonb_typeof(multiplicadores) = 'array'),
  UNIQUE (tenant_id, rede_id, padrao_id)
);
ALTER TABLE plat.rede_epanet_padrao ADD CONSTRAINT rede_epanet_padrao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_rede_epanet_padrao_tenant ON plat.rede_epanet_padrao (tenant_id);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_epanet_curva', 'rede_epanet_padrao'] LOOP
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
  ('redes/epanet_importar', 'importação de arquivo EPANET .inp enfileirada'),
  ('redes/epanet_exportar', 'rede exportada como arquivo EPANET .inp')
ON CONFLICT (nome) DO NOTHING;
