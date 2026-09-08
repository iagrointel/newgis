-- 20260907T1634_geoparquet: GeoParquet como formato de trabalho para o grande (item
-- L2-15-a-geoparquet-bucket-catalogo). Carimbo de tempo, não número sequencial (ADR 0014).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Reusa DE PROPÓSITO o que o item L0-04-h-exportar (ADR 0018, wt/l004h-exportar-limpo, mesclado nesta
-- trilha) já construiu: `plat.exportacao` é o irmão deste item para um ÚNICO arquivo efêmero (7 dias, pasta
-- do usuário); `plat.geoparquet_job` aqui é o histórico do job DURADOURO (o resultado vira item do catálogo,
-- não some) que pode gerar VÁRIOS arquivos particionados e, no modo `arquivar`, apagar linha de origem depois
-- de conferir a contagem. Mesmo padrão de tabela/RLS/gatilho de estado final da 20260907T0141.
--
-- O que entra:
--   1. tipo_item `parquet` — item do catálogo que representa um ou mais arquivos GeoParquet no bucket do
--      inquilino, com esquema, contagem, bbox, sha256 por arquivo e proveniência (ADR 0004 seção 3).
--   2. plat.geoparquet_job — uma linha por RODADA de geração/atualização/arquivamento (auditoria: quem gerou
--      o quê, quando, com que partição). RLS por inquilino.
--   3. plat.geoparquet_arquivar_confirmar(job_id, linhas_esperadas) — SECURITY DEFINER: o DELETE da origem só
--      é permitido depois que o job já contou as linhas no(s) arquivo(s) gerado(s) e elas batem com o
--      esperado (contrato do portão: "contagem no Parquet = contagem apagada no banco").
--   4. eventos `geoparquet/gerar` e `geoparquet/arquivar`.
--
-- Nenhum privilégio novo: gerar usa `conteudo.exportar` (mesmo do L0-04-h); arquivar (apaga linha de origem)
-- exige ADEMAIS `conteudo.apagar_tudo` (já existe, administrativo) — ver app/geoparquet/rotas.py.

CREATE TABLE IF NOT EXISTS plat.geoparquet_job (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  usuario_id        int NOT NULL REFERENCES plat.usuario(id),
  item_id           uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,   -- a camada/tabela de origem
  modo              text NOT NULL DEFAULT 'exportar' CHECK (modo IN ('exportar','arquivar')),
  parametros        jsonb NOT NULL DEFAULT '{}'::jsonb,  -- where, particionar_por, grupo_linhas, coluna_data
  estado            text NOT NULL DEFAULT 'pendente'
                    CHECK (estado IN ('pendente','gerando','pronta','falhou','cancelada')),
  job_id            uuid,                                 -- id em plat.job (fila)
  catalogo_item_id  uuid REFERENCES plat.item(id) ON DELETE SET NULL,  -- item tipo 'parquet' publicado/atualizado
  versao            int,                                  -- nº sequencial desta fonte+partição (1ª rodada = 1)
  arquivos          jsonb NOT NULL DEFAULT '[]'::jsonb,    -- [{chave,sha256,bytes,linhas,bbox,particao,novo}]
  particoes_alteradas jsonb NOT NULL DEFAULT '[]'::jsonb,  -- chaves de partição cujo conteúdo mudou nesta rodada
  linhas_total      bigint,
  bytes_total       bigint,
  linhas_arquivadas bigint,                                -- só modo=arquivar: linhas apagadas da origem
  duracao_ms        int,
  erro              text,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  concluido_em      timestamptz
);
CREATE INDEX IF NOT EXISTS ix_geoparquet_job_tenant ON plat.geoparquet_job (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_geoparquet_job_item   ON plat.geoparquet_job (item_id);
CREATE INDEX IF NOT EXISTS ix_geoparquet_job_catalogo ON plat.geoparquet_job (catalogo_item_id);

ALTER TABLE plat.geoparquet_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.geoparquet_job FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_geoparquet_job ON plat.geoparquet_job;
CREATE POLICY p_geoparquet_job ON plat.geoparquet_job FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- estado final imutável (mesmo padrão de plat.exportacao_estado_final_imutavel)
CREATE OR REPLACE FUNCTION plat.geoparquet_job_estado_final_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('falhou','cancelada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'geoparquet_job_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS geoparquet_job_estado_final_imutavel ON plat.geoparquet_job;
CREATE TRIGGER geoparquet_job_estado_final_imutavel BEFORE UPDATE ON plat.geoparquet_job
  FOR EACH ROW EXECUTE FUNCTION plat.geoparquet_job_estado_final_imutavel();

-- ---------------------------------------------------------------- confirmação do expurgo (modo arquivar)
-- SECURITY DEFINER só para ler o job de QUALQUER inquilino a partir do id (o job em si roda sob RLS do
-- próprio inquilino quando faz o DELETE de origem — esta função é chamada DEPOIS, para o registro final);
-- mesmo mecanismo de plat.exportacoes_expirar_candidatos (20260907T0141).
CREATE OR REPLACE FUNCTION plat.geoparquet_arquivar_confirmar(p_job_id uuid, p_linhas_apagadas bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.geoparquet_job SET linhas_arquivadas = p_linhas_apagadas
  WHERE id = p_job_id AND modo = 'arquivar';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'geoparquet_job_nao_encontrado_ou_nao_e_arquivar' USING ERRCODE = 'no_data_found';
  END IF;
END $$;
GRANT EXECUTE ON FUNCTION plat.geoparquet_arquivar_confirmar(uuid, bigint) TO plat_app;

-- ---------------------------------------------------------------- quantos jobs de geoparquet o usuário tem em
-- curso (mesmo mecanismo de plat.exportacoes_em_curso, 20260907T0141)
CREATE OR REPLACE FUNCTION plat.geoparquet_jobs_em_curso(p_usuario_id int) RETURNS int
LANGUAGE sql STABLE AS $$
  SELECT count(*)::int FROM plat.geoparquet_job
  WHERE usuario_id = p_usuario_id AND estado IN ('pendente','gerando');
$$;
GRANT EXECUTE ON FUNCTION plat.geoparquet_jobs_em_curso(int) TO plat_app;

-- ---------------------------------------------------------------- tipo_item `parquet`
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('parquet', 'camada', 'GeoParquet', 'um ou mais arquivos GeoParquet no bucket do inquilino, gerados a partir '
   'de camada, vista ou histórico de fluxo, com esquema/contagem/bbox/sha256 e proveniência (item L2-15-a)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["origem","arquivos","linhas_total","esquema","proveniencia"],
     "properties":{
       "origem":{"type":"object","additionalProperties":false,"required":["item_id","schema","tabela"],
         "properties":{"item_id":{"type":"string","format":"uuid"},
           "tipo_item":{"type":"string","maxLength":64},
           "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
           "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"}}},
       "particionar_por":{"type":["object","null"],"additionalProperties":false,
         "properties":{"coluna":{"type":"string","maxLength":63},
           "grao":{"type":"string","enum":["valor","ano_mes"]}}},
       "grupo_linhas":{"type":"integer","minimum":1000,"maximum":1000000},
       "crs":{"type":"integer","minimum":1,"maximum":999999},
       "esquema":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,
         "required":["nome","tipo"],"properties":{"nome":{"type":"string","maxLength":63},
           "tipo":{"type":"string","maxLength":64}}}},
       "arquivos":{"type":"array","items":{"type":"object","additionalProperties":false,
         "required":["chave","sha256","bytes","linhas"],
         "properties":{
           "chave":{"type":"string","maxLength":300},
           "sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
           "bytes":{"type":"integer","minimum":0},
           "linhas":{"type":"integer","minimum":0},
           "bbox":{"type":["array","null"],"minItems":4,"maxItems":4,"items":{"type":"number"}},
           "particao":{"type":"object"}}}},
       "linhas_total":{"type":"integer","minimum":0},
       "bytes_total":{"type":"integer","minimum":0},
       "proveniencia":{"type":"object","additionalProperties":false,
         "required":["item_id","versao","gerado_em","modo"],
         "properties":{
           "item_id":{"type":"string","format":"uuid"},
           "versao":{"type":"integer","minimum":1},
           "gerado_em":{"type":"string"},
           "modo":{"type":"string","enum":["exportar","arquivar"]},
           "job_id":{"type":"string","format":"uuid"},
           "linhas_arquivadas":{"type":"integer","minimum":0}}}}}'::jsonb,
   1, 'camada', '/static/js/catalogo/tipos/parquet.js', '{tabela}', true, 'L2-15')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('geoparquet/gerar', 'GeoParquet gerado/atualizado no bucket e registrado no catálogo (item L2-15-a)'),
  ('geoparquet/arquivar', 'histórico exportado para GeoParquet e expurgado da tabela de origem (item L2-15-a)'),
  ('geoparquet/exportar_pedido', 'job de geração de GeoParquet pedido (modo exportar; item L2-15-a)'),
  ('geoparquet/arquivar_pedido', 'job de geração de GeoParquet pedido (modo arquivar; item L2-15-a)'),
  ('geoparquet/arquivos_listados', 'URLs assinadas de um item GeoParquet foram pedidas (item L2-15-a)')
ON CONFLICT (nome) DO NOTHING;
