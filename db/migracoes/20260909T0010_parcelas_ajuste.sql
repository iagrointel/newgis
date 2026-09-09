-- L4-parcelas-03-ajuste-e-qualidade: categoria de precisão declarada por ponto e por linha (a
-- classe de exatidão da paridade §13, à la aboutmeasurementaccuracy), a tabela de versão do
-- ajuste plat.parcela_ajuste e os tipos de evento do analisar/aplicar e da camada de qualidade.
-- Par: docs/PARIDADE_PARCELAS.md (seção 13), app/parcelas/ajuste.py, app/parcelas/qualidade.py.

-- Categoria declarada do PONTO: 'controle' é o datum da rede (o ajuste não move), 'apoio' é o
-- resto. A precisão explícita (precisao_xy_m, do item 01) vence quando preenchida; a categoria
-- dá o padrão quando o ponto não declara número.
ALTER TABLE plat.parcela_ponto ADD COLUMN IF NOT EXISTS categoria text NOT NULL DEFAULT 'apoio';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parcela_ponto_categoria_check'
                 AND conrelid = 'plat.parcela_ponto'::regclass) THEN
    ALTER TABLE plat.parcela_ponto ADD CONSTRAINT parcela_ponto_categoria_check
      CHECK (categoria IN ('controle', 'apoio'));
  END IF;
END $$;
COMMENT ON COLUMN plat.parcela_ponto.categoria IS
  'Classe de exatidão declarada: controle (datum, não se move no ajuste) ou apoio. O padrão de
  sigma vem da tabela de categorias em app/parcelas/ajuste.py; precisao_xy_m preenchida vence.';

-- Categoria declarada da LINHA: 'medido' (instrumento, padrão), 'escritura' (documento) e
-- 'derivado' (malha importada, sem medida COGO — nunca entra no ajuste por não ter rumo/dist).
ALTER TABLE plat.parcela_linha ADD COLUMN IF NOT EXISTS categoria text NOT NULL DEFAULT 'medido';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parcela_linha_categoria_check'
                 AND conrelid = 'plat.parcela_linha'::regclass) THEN
    ALTER TABLE plat.parcela_linha ADD CONSTRAINT parcela_linha_categoria_check
      CHECK (categoria IN ('medido', 'escritura', 'derivado'));
  END IF;
END $$;
COMMENT ON COLUMN plat.parcela_linha.categoria IS
  'Classe de exatidão da medida COGO: medido, escritura ou derivado. O par (sigma_distancia_m,
  sigma_rumo_s) padrão vem de app/parcelas/ajuste.py; precisao_dist_cm/precisao_rumo_s vencem.';

-- A versão do ajuste: cada APLICAÇÃO grava uma linha com o relatório completo (a análise é o
-- antes, a aplicação é o depois, e a linha é a versão que o portão exige). O ajuste NÃO apaga
-- nada: as coordenadas anteriores ficam no relatório da versão anterior (append-only).
CREATE TABLE IF NOT EXISTS plat.parcela_ajuste (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  analise       jsonb NOT NULL CHECK (jsonb_typeof(analise) = 'object'),  -- relatório integral (pontos, linhas, resíduos)
  sigma_zero    double precision NOT NULL,
  iteracoes     int NOT NULL,
  redundancia   int NOT NULL,
  deslocamento_maximo_m double precision NOT NULL,
  pontos_ajustados int NOT NULL,
  linhas_observadas int NOT NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  CHECK (sigma_zero >= 0 AND iteracoes >= 1 AND redundancia >= 0
         AND deslocamento_maximo_m >= 0 AND pontos_ajustados >= 0 AND linhas_observadas >= 0)
);
CREATE INDEX IF NOT EXISTS ix_parcela_ajuste_tenant ON plat.parcela_ajuste (tenant_id, criado_em DESC);
COMMENT ON TABLE plat.parcela_ajuste IS
  'Versão de cada aplicação do ajuste por mínimos quadrados (analyzeByLSA/applyLSA): relatório
  completo em analise (jsonb) + resumo em colunas. Inquilino por tenant_id com RLS.';

ALTER TABLE plat.parcela_ajuste ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_parcela_ajuste ON plat.parcela_ajuste;
CREATE POLICY p_parcela_ajuste ON plat.parcela_ajuste FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

GRANT SELECT ON plat.parcela_ajuste TO plat_leitor;

-- Tipos de evento (tests/api/eventos_esperados.py cita cada um; sem a linha aqui a rota cai em
-- 500 ao registrar o evento — mesma classe de erro da migração 20260908T2330).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('parcelas/analyze_lsa', 'ajuste por mínimos quadrados analisado (análise, sem escrita)'),
  ('parcelas/apply_lsa', 'ajuste por mínimos quadrados aplicado (pontos movidos, versão gravada)'),
  ('parcelas/qualidade', 'camada de lacunas e sobreposições gerada (Find Gaps and Overlaps)')
ON CONFLICT (nome) DO NOTHING;
