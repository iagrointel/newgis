-- 20260906T2151_exportacao_camada (item L0-04-h-exportar): exportação de camada/vista como job
-- (ogr2ogr, 11 formatos). Quatro peças:
-- 1) privilégio novo `conteudo.exportar` (não administrativo; editor e admin por padrão — o visualizador e o
--    campo NÃO exportam, é o que o portão testa com o 403). O vocabulário passa de 47 para 48 (espelho em
--    app/auth/privilegios.py, conferido por tests/api/test_privilegios_declarados.py).
-- 2) opção do DONO da camada "permitir que outros exportem" (padrão desligado, como a Esri): propriedade
--    `exportacao.permitir_outros` no esquema v3 de camada_vetorial. Sem ela, quem não é dono (mesmo vendo a
--    camada por compartilhamento) recebe 403 ao exportar. A vista não tem opção própria: vale a da camada
--    primária (a vista é um recorte; a permissão é do dado).
-- 3) validade do arquivo gerado (7 dias): coluna `plat.item.expira_em` (NULL = sem validade, como sempre foi)
--    + função `plat.exportacao_expirar` (lista os vencidos, no mesmo desenho de plat.lixeira_expurgar) +
--    `plat.exportacao_expurgar` (DELETE físico só de item vencido). O periódico `exportacao.expirar`
--    (app/exportacao/tarefas.py) destrói o objeto no armazenamento e expurga o registro; quem chama a função
--    com relógio simulado em dev é o teste do portão ("arquivo expira e some em 7 dias").
-- 4) esquema v2 do tipo `arquivo`: propriedade opcional `exportacao` (camada_id, formato, parâmetros) para
--    identificar o resultado e alimentar GET /api/exportacoes/{id} sem tabela nova.
-- Idempotente; sem BEGIN/COMMIT.

INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('conteudo.exportar', 'conteudo',
   'exportar camada/vista para arquivo (shapefile, GeoPackage, GeoJSON, CSV, planilha, KML, DXF, GeoParquet)',
   false)
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao,
                                 administrativo = EXCLUDED.administrativo;

INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('editor', 'conteudo.exportar'),
  ('admin',  'conteudo.exportar')
ON CONFLICT (perfil, privilegio) DO NOTHING;

-- ---------------------------------------------------------------- validade no item
ALTER TABLE plat.item ADD COLUMN IF NOT EXISTS expira_em timestamptz;
CREATE INDEX IF NOT EXISTS ix_item_expira ON plat.item (expira_em) WHERE expira_em IS NOT NULL;

-- ---------------------------------------------------------------- tipo_item camada_vetorial: esquema v3
-- (acrescenta exportacao.permitir_outros; v2 da 029 continua válida para leitura — a propriedade é opcional)
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

-- ---------------------------------------------------------------- tipo_item arquivo: esquema v2 (marca o
-- resultado de uma exportação; quem grava é o job exportacao.camada)
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                            tem_dado_fisico, linha_dona) VALUES
  ('arquivo', 'arquivo', 'Arquivo', 'arquivo guardado no armazenamento de objetos',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["chave","sha256","bytes","content_type","nome_original"],
     "properties":{"chave":{"type":"string","maxLength":512},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
       "bytes":{"type":"integer","minimum":0},"content_type":{"type":"string","maxLength":255},"nome_original":{"type":"string","maxLength":255},
       "exportacao":{"type":"object","additionalProperties":true}}}'::jsonb,
   2, 'arquivo', '/static/js/catalogo/tipos/arquivo.js', '{}', true, 'L0-11')
ON CONFLICT (nome) DO UPDATE SET
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

-- ---------------------------------------------------------------- expiração dos arquivos de exportação.
-- Mesmo desenho de plat.lixeira_expurgar (011): SECURITY DEFINER, contexto obrigatório, o inquilino técnico
-- `plataforma` varre todos; inquilino comum só vê/apaga o dele. Só item tipo 'arquivo' COM expira_em vencido —
-- nenhum outro item da instalação tem expira_em preenchido (a coluna nasce aqui, para este fim).
CREATE OR REPLACE FUNCTION plat.exportacao_expirar(p_agora timestamptz DEFAULT now())
RETURNS TABLE (item_id uuid, tenant_id int, dados jsonb, miniatura_chave text, tamanho_bytes bigint, titulo text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY
    SELECT i.id, i.tenant_id, i.dados, i.miniatura_chave, i.tamanho_bytes, i.titulo
    FROM plat.item i
    WHERE i.tipo = 'arquivo' AND i.expira_em IS NOT NULL AND i.expira_em <= p_agora
      AND i.apagado_em IS NULL
      AND (t_plataforma OR i.tenant_id = t_ctx)
    ORDER BY i.expira_em;
END $$;

CREATE OR REPLACE FUNCTION plat.exportacao_expurgar(p_item uuid, p_agora timestamptz DEFAULT now()) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  DELETE FROM plat.item
   WHERE id = p_item AND tipo = 'arquivo' AND expira_em IS NOT NULL AND expira_em <= p_agora
     AND (t_plataforma OR tenant_id = t_ctx);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

GRANT EXECUTE ON FUNCTION plat.exportacao_expirar(timestamptz) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.exportacao_expurgar(uuid, timestamptz) TO plat_app;

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/exportar', 'exportação de camada/vista para arquivo solicitada (job exportacao.camada)'),
  ('exportacoes/expirar', 'arquivo de exportação apagado ao vencer a validade')
ON CONFLICT (nome) DO NOTHING;
