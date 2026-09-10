-- 20260906T2048_rede_topologia_area_suja: AREA SUJA da topologia derivada (item L4-01-b-topologia-derivada;
-- complementa 20260906T2000; a decisão está no ADR docs/adr/20260906T2048-area-suja-e-applyedits.md).
--
-- Por que existe: a refutação exigida do item manda o adversário editar uma feição via applyEdits e conferir
-- que "a topologia marca área suja". Sem esta tabela a única resposta seria reconstruir a rede inteira a cada
-- edição. O modelo é o do ArcGIS Utility Network: a EDIÇÃO não toca o índice derivado — grava um polígono
-- (envelope da geometria velha U nova, expandido pela tolerância da rede) marcando onde a topologia gravada
-- ficou POSSIVELMENTE errada; a próxima chamada de `habilitar` reconstrói tudo e apaga as áreas sujas da rede.
-- A manutenção INCREMENTAL (reconstruir só a área suja) segue fora desta passagem — fronteira honesta,
-- docs/rede/TOPOLOGIA.md seção 6.
--
-- `motivo`: 'criacao' (feição nova sobre topologia já construída), 'edicao' (geometria/atributo alterado),
-- 'remocao' (feição apagada). `feicao_id` é o id da feição de rede (`rede_feicao_ponto` ou
-- `rede_feicao_linha`) — sem FK de propósito: na remoção a feição já não existe quando a área é consultada, e
-- a área suja tem de sobreviver a ela. Dado do INQUILINO (RLS), como as demais tabelas da linha.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede_topo_area_suja (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  motivo        text NOT NULL CHECK (motivo IN ('criacao', 'edicao', 'remocao')),
  feicao_id     uuid,
  geom          geometry(Polygon, 4326) NOT NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_topo_area_suja_tenant ON plat.rede_topo_area_suja (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_area_suja_rede ON plat.rede_topo_area_suja (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_area_suja_geom ON plat.rede_topo_area_suja USING gist (geom);
ALTER TABLE plat.rede_topo_area_suja ADD CONSTRAINT rede_topo_area_suja_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

DO $$
BEGIN
  ALTER TABLE plat.rede_topo_area_suja ENABLE ROW LEVEL SECURITY;
  DROP POLICY IF EXISTS p_rede_topo_area_suja_ler ON plat.rede_topo_area_suja;
  CREATE POLICY p_rede_topo_area_suja_ler ON plat.rede_topo_area_suja FOR SELECT TO plat_app
    USING (tenant_id = plat.tenant_atual());
  DROP POLICY IF EXISTS p_rede_topo_area_suja_inserir ON plat.rede_topo_area_suja;
  CREATE POLICY p_rede_topo_area_suja_inserir ON plat.rede_topo_area_suja FOR INSERT TO plat_app
    WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
  DROP POLICY IF EXISTS p_rede_topo_area_suja_alterar ON plat.rede_topo_area_suja;
  CREATE POLICY p_rede_topo_area_suja_alterar ON plat.rede_topo_area_suja FOR UPDATE TO plat_app
    USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
  DROP POLICY IF EXISTS p_rede_topo_area_suja_apagar ON plat.rede_topo_area_suja;
  CREATE POLICY p_rede_topo_area_suja_apagar ON plat.rede_topo_area_suja FOR DELETE TO plat_app
    USING (tenant_id = plat.tenant_atual());
  GRANT SELECT, INSERT, UPDATE, DELETE ON plat.rede_topo_area_suja TO plat_app;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/feicao_editar', 'feição de rede editada via applyEdits (adds/updates/deletes; área suja marcada)')
ON CONFLICT (nome) DO NOTHING;
