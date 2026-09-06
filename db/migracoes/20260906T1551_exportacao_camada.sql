-- 20260906T1551_exportacao_camada: exportação de camada/tabela como job (item L0-04-h-exportar; ADR 0023).
-- Carimbo de tempo, não número sequencial (ADR 0014 / BRIEF_WORKTREES: a família 001-049 está fechada).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- O que entra:
--   1. plat.exportacao — uma linha por pedido de exportação (formato, filtro, campos, CRS, codificação, estado,
--      job, arquivo gerado, validade). RLS por inquilino, igual a plat.importacao (029_ingestao_vetor.sql).
--   2. privilégio `conteudo.exportar` (grupo conteudo, não administrativo; perfis editor e admin, como
--      `conteudo.publicar_camada`) — espelho de app/auth/privilegios.py, conferido por
--      tests/api/test_privilegios_declarados.py.
--   3. tipo_item camada_vetorial esquema v3: acrescenta o bloco `exportacao` ao JSON Schema do item
--      (`permitir_outros`, padrão false — a opção do dono do item, como o "Allow others to export to different
--      formats" da Esri). `additionalProperties:false` no esquema v2 recusaria a chave nova sem esta versão.
--   4. plat.exportacoes_expirar_candidatos() — SECURITY DEFINER (mesmo mecanismo de
--      plat.uploads_expirar_candidatos, 046): o periódico roda sob o inquilino técnico `plataforma` e precisa
--      enxergar exportação vencida de QUALQUER inquilino; só LÊ, quem apaga o objeto é o Python no contexto
--      do inquilino de cada linha.
--   5. eventos camadas/exportar e camadas/exportar_baixar.
--
-- Por que `arquivo_item_id` referencia plat.item com ON DELETE SET NULL e não CASCADE: o item de arquivo é o
-- que o usuário vê na pasta dele e pode apagar à mão; apagar o item não pode apagar o histórico da exportação
-- (que é registro de auditoria: quem exportou o quê, quando, com que filtro).

CREATE TABLE IF NOT EXISTS plat.exportacao (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  usuario_id        int NOT NULL REFERENCES plat.usuario(id),
  item_id           uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,   -- a camada de origem
  formato           text NOT NULL,
  parametros        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- where, bbox, campos, srid_saida, codificacao, csv
  estado            text NOT NULL DEFAULT 'pendente'
                    CHECK (estado IN ('pendente','gerando','pronta','falhou','cancelada','expirada')),
  job_id            uuid,
  arquivo_item_id   uuid REFERENCES plat.item(id) ON DELETE SET NULL,           -- item na pasta do usuário
  chave             text,                                  -- chave do objeto no Garage (app/objetos.py)
  sha256            text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  bytes             bigint,
  feicoes           bigint,
  duracao_ms        int,
  erro              text,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  concluido_em      timestamptz,
  expira_em         timestamptz NOT NULL DEFAULT now() + interval '7 days'
);
CREATE INDEX IF NOT EXISTS ix_exportacao_tenant  ON plat.exportacao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_exportacao_item    ON plat.exportacao (item_id);
CREATE INDEX IF NOT EXISTS ix_exportacao_usuario ON plat.exportacao (usuario_id, estado);
CREATE INDEX IF NOT EXISTS ix_exportacao_expira  ON plat.exportacao (expira_em) WHERE estado = 'pronta';

ALTER TABLE plat.exportacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.exportacao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_exportacao ON plat.exportacao;
CREATE POLICY p_exportacao ON plat.exportacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- estado final é imutável (mesmo padrão de plat.importacao_estado_final_imutavel, 029)
CREATE OR REPLACE FUNCTION plat.exportacao_estado_final_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('falhou','cancelada','expirada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'exportacao_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS exportacao_estado_final_imutavel ON plat.exportacao;
CREATE TRIGGER exportacao_estado_final_imutavel BEFORE UPDATE ON plat.exportacao
  FOR EACH ROW EXECUTE FUNCTION plat.exportacao_estado_final_imutavel();

-- ---------------------------------------------------------------- quantas exportações o usuário tem em curso
-- (limite por USUÁRIO da refutação do item: 5 exportações em paralelo da mesma camada). STABLE, sob a RLS de
-- quem chama — nunca vê linha de outro inquilino.
CREATE OR REPLACE FUNCTION plat.exportacoes_em_curso(p_usuario_id int) RETURNS int
LANGUAGE sql STABLE AS $$
  SELECT count(*)::int FROM plat.exportacao
  WHERE usuario_id = p_usuario_id AND estado IN ('pendente','gerando');
$$;
GRANT EXECUTE ON FUNCTION plat.exportacoes_em_curso(int) TO plat_app;

-- ---------------------------------------------------------------- expurgo das vencidas (periódico
-- exportacao.expirar; mesmo mecanismo de plat.uploads_expirar_candidatos da 046)
-- Sem parâmetro de propósito: a validade já está gravada em cada linha (`expira_em`, 7 dias por padrão, ver
-- limites.EXPORTACAO_VALIDADE_DIAS). Um parâmetro "dias" aqui seria uma segunda fonte de verdade e permitiria
-- ao chamador encurtar a validade de exportação alheia; para testar a expiração, adianta-se `expira_em` da
-- própria linha (a RLS já garante que só a do próprio inquilino).
CREATE OR REPLACE FUNCTION plat.exportacoes_expirar_candidatos()
RETURNS TABLE (id uuid, tenant_id int, usuario_id int, chave text, arquivo_item_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT e.id, e.tenant_id, e.usuario_id, e.chave, e.arquivo_item_id
  FROM plat.exportacao e
  WHERE e.estado = 'pronta' AND e.expira_em < now()
  ORDER BY e.expira_em;
$$;
GRANT EXECUTE ON FUNCTION plat.exportacoes_expirar_candidatos() TO plat_app;

-- ---------------------------------------------------------------- privilégio novo (espelho de
-- app/auth/privilegios.py; a lista de perfis segue `conteudo.publicar_camada`: editor e admin)
INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('conteudo.exportar', 'conteudo', 'exportar camada para outros formatos (shapefile, GeoPackage, CSV, ...)', false)
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao,
                                 administrativo = EXCLUDED.administrativo;
INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('editor', 'conteudo.exportar'),
  ('admin',  'conteudo.exportar')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- tipo_item camada_vetorial: esquema v3
-- (v2 = 029_ingestao_vetor.sql; acrescenta só o bloco `exportacao`)
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('camada_vetorial', 'camada', 'Camada vetorial', 'camada vetorial hospedada ou referenciada (tabela PostGIS)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["schema","tabela","geometria","srid","campos","fonte"],
     "properties":{
       "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "geometria":{"type":"string","enum":["Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon","Geometry","nenhuma"]},
       "srid":{"type":"integer","minimum":1,"maximum":999999},
       "campos":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,"required":["nome","tipo"],
                 "properties":{"nome":{"type":"string","maxLength":63},"tipo":{"type":"string","maxLength":64},"alias":{"type":"string","maxLength":200}}}},
       "fonte":{"type":"string","enum":["hospedada","referenciada"]},
       "edicao":{"type":"object","additionalProperties":false,"properties":{"habilitada":{"type":"boolean"}}},
       "exportacao":{"type":"object","additionalProperties":false,"properties":{"permitir_outros":{"type":"boolean"}}},
       "procedencia":{"type":"object","additionalProperties":true},
       "estatisticas":{"type":"object","additionalProperties":true},
       "importacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   3, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/exportar', 'exportação de camada pedida (item L0-04-h)'),
  ('camadas/exportar_baixar', 'arquivo de exportação baixado')
ON CONFLICT (nome) DO NOTHING;
