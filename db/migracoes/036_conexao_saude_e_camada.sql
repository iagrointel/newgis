-- 036_conexao_saude_e_camada: dois itens pequenos sobre `plat.conexao` (L6-02-a, entregue).
--
-- L6-02-l-saude: histórico dos últimos testes de saúde (`plat.conexao_saude_historico`, 30 linhas mais
-- recentes por conexão — "últimos 10" do portão é o que a tela mostra, 30 é a folga de guarda), verificação
-- PERIÓDICA (reaproveita o relógio do L0-05: `app/conexao/tarefas.py` roda como periódico no inquilino
-- técnico `plataforma`, mesmo padrão de `plat.jobs_expurgar`/`plat.manutencao_analyze` — SECURITY DEFINER
-- que só executa sob `plat.tenant_atual() = 'plataforma'`, para poder ler/escrever CONEXÕES DE QUALQUER
-- INQUILINO a partir de um job que roda em um só) e estado agregado (`plat.v_conexao_saude`: ok/degradado/
-- fora, computado da JANELA das últimas 5 verificações — "fora" = a mais recente falhou, "degradado" = a
-- mais recente passou mas alguma das últimas 5 falhou, "ok" = as últimas 5 (ou menos, se ainda não houver
-- 5) passaram — nunca dois estados por engano, porque as três condições do CASE são mutuamente exclusivas
-- e cobrem todo o universo: nunca_testada (sem saude), fora (última=false), degradado (última=true E
-- alguma falha), ok (o resto)).
--
-- L6-05-proveniencia-camada-externa: tipo_item 'conexao' (021/v2) ganha a propriedade `procedencia` no
-- esquema (v3; a mesma chave que `dados.procedencia` já usa em toda a casa — `app/catalogo/metadado.py`
-- monta o `dataQualityInfo`/lineage do ISO 19139 dela, `app/ingestao/carregar.py` já a preenche para
-- camada_vetorial) e o enum de `protocolo` fica igual ao `CHECK` de `plat.conexao.tipo` (stac/geoparquet/
-- pmtiles entraram na 030 depois da 021; as duas listas mudam juntas, comentário da 030). `app/conexao/
-- proveniencia.py` lê o que o serviço externo DECLARA (GetCapabilities/AccessConstraints, `copyrightText`
-- do ArcGIS REST, `license` do STAC/OGC API) e popula esse bloco quando a camada é publicada por
-- `POST /api/conexoes/{id}/publicar` — nunca um valor padrão (é literalmente a refutação do item).
--
-- Numeração 036 (035 = acervo_lgpd, de outra trilha concorrente neste mesmo turno). Idempotente. Sem
-- BEGIN/COMMIT. Aplicada como postgres (dono das funções SECURITY DEFINER, que por isso ignoram a RLS de
-- `plat.conexao`/`plat.conexao_saude_historico` sem precisar de FORCE ROW LEVEL SECURITY — mesmo mecanismo
-- de `plat.jobs_expurgar`, 006).

-- ---------------------------------------------------------------- histórico de teste de saúde
CREATE TABLE IF NOT EXISTS plat.conexao_saude_historico (
  id            bigserial PRIMARY KEY,
  conexao_id    uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  verificada_em timestamptz NOT NULL DEFAULT now(),
  ok            boolean NOT NULL,
  status        int,
  mensagem      text,
  latencia_ms   int
);
CREATE INDEX IF NOT EXISTS ix_conexao_saude_historico_conexao ON plat.conexao_saude_historico (conexao_id, verificada_em DESC);
CREATE INDEX IF NOT EXISTS ix_conexao_saude_historico_tenant ON plat.conexao_saude_historico (tenant_id);

ALTER TABLE plat.conexao_saude_historico ENABLE ROW LEVEL SECURITY;

-- só leitura para plat_app (RLS por inquilino); nenhuma política de escrita — só a função SECURITY DEFINER
-- abaixo grava (dono da tabela, ignora RLS), do mesmo jeito que ninguém grava em plat.versao_migracao direto.
DROP POLICY IF EXISTS p_conexao_saude_historico_ler ON plat.conexao_saude_historico;
CREATE POLICY p_conexao_saude_historico_ler ON plat.conexao_saude_historico FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

REVOKE ALL ON plat.conexao_saude_historico FROM PUBLIC;
GRANT SELECT ON plat.conexao_saude_historico TO plat_app;

-- ---------------------------------------------------------------- candidatas a verificar (cruza inquilinos)
CREATE OR REPLACE FUNCTION plat.conexao_saude_candidatas(p_intervalo interval, p_limite int)
RETURNS TABLE (id uuid, tenant_id int, tipo text, url text, credencial_cifrada text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'verificacao de saude de conexao so no contexto do inquilino tecnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  SELECT c.id, c.tenant_id, c.tipo, c.url, c.credencial_cifrada
  FROM plat.conexao c
  WHERE c.saude_verificada_em IS NULL OR c.saude_verificada_em < now() - p_intervalo
  ORDER BY c.saude_verificada_em ASC NULLS FIRST
  LIMIT p_limite;
END $$;

-- ---------------------------------------------------------------- registra 1 resultado (bypassa RLS, grava histórico e poda)
-- Duas chamadoras legítimas: (1) o PRÓPRIO inquilino testando manualmente a sua conexão (POST /api/conexoes/{id}/
-- testar, já existia desde L6-02-a — só não gravava histórico ainda) e (2) o periódico rodando no inquilino
-- técnico `plataforma`, verificando conexões de QUALQUER inquilino. Nenhuma outra combinação passa.
CREATE OR REPLACE FUNCTION plat.conexao_saude_registrar(
  p_id uuid, p_ok boolean, p_status int, p_mensagem text, p_latencia_ms int, p_manter int DEFAULT 30
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int; v_saude text; v_atual int;
BEGIN
  SELECT tenant_id INTO v_tenant FROM plat.conexao WHERE id = p_id;
  IF v_tenant IS NULL THEN
    RETURN; -- a conexão foi apagada entre a candidatura e o registro (ou nunca existiu): nunca erro
  END IF;
  v_atual := plat.tenant_atual();
  IF v_atual IS DISTINCT FROM v_tenant
     AND v_atual IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'sem permissao para registrar a saude desta conexao' USING ERRCODE = 'insufficient_privilege';
  END IF;
  v_saude := CASE WHEN p_ok THEN 'ok' ELSE 'erro' END;
  UPDATE plat.conexao
     SET saude = v_saude, saude_mensagem = p_mensagem, saude_latencia_ms = p_latencia_ms, saude_verificada_em = now()
   WHERE id = p_id;
  INSERT INTO plat.conexao_saude_historico(conexao_id, tenant_id, ok, status, mensagem, latencia_ms)
  VALUES (p_id, v_tenant, p_ok, p_status, p_mensagem, p_latencia_ms);
  DELETE FROM plat.conexao_saude_historico
   WHERE conexao_id = p_id
     AND id NOT IN (
       SELECT id FROM plat.conexao_saude_historico WHERE conexao_id = p_id ORDER BY verificada_em DESC LIMIT p_manter
     );
END $$;

REVOKE ALL ON FUNCTION plat.conexao_saude_candidatas(interval, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.conexao_saude_registrar(uuid, boolean, int, text, int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.conexao_saude_candidatas(interval, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.conexao_saude_registrar(uuid, boolean, int, text, int, int) TO plat_app;

-- ---------------------------------------------------------------- estado agregado (ok/degradado/fora) + disponibilidade 30d
CREATE OR REPLACE VIEW plat.v_conexao_saude WITH (security_invoker = true) AS
SELECT
  c.id AS conexao_id,
  CASE
    WHEN c.saude = 'nunca_testada'  THEN 'nunca_testada'
    WHEN jan.ultima_ok IS FALSE     THEN 'fora'
    WHEN jan.alguma_falha           THEN 'degradado'
    ELSE 'ok'
  END AS estado_saude,
  disp.total AS disponibilidade_30d_total,
  disp.ok    AS disponibilidade_30d_ok,
  CASE WHEN disp.total > 0 THEN round(disp.ok::numeric / disp.total * 100, 1) END AS disponibilidade_30d_pct
FROM plat.conexao c
LEFT JOIN LATERAL (
  SELECT (array_agg(h.ok ORDER BY h.verificada_em DESC))[1] AS ultima_ok,
         bool_or(NOT h.ok) AS alguma_falha
  FROM (
    SELECT ok, verificada_em FROM plat.conexao_saude_historico WHERE conexao_id = c.id ORDER BY verificada_em DESC LIMIT 5
  ) h
) jan ON true
LEFT JOIN LATERAL (
  SELECT count(*) AS total, count(*) FILTER (WHERE ok) AS ok
  FROM plat.conexao_saude_historico
  WHERE conexao_id = c.id AND verificada_em >= now() - interval '30 days'
) disp ON true;

REVOKE ALL ON plat.v_conexao_saude FROM PUBLIC;
GRANT SELECT ON plat.v_conexao_saude TO plat_app;

-- ---------------------------------------------------------------- tipo_item 'conexao': esquema v2 -> v3 (procedência)
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('conexao', 'ferramenta', 'Conexão',
   'fonte de dado externa (segredo fica no cofre, nunca em dados) ou fonte do acervo da casa (protocolo "acervo", '
   'referenciada por parametros.fonte_id, nunca copiada); camada publicada a partir de uma plat.conexao '
   '(parametros.conexao_id) carrega bloco de procedência lido do serviço, nunca um valor padrão (item '
   'L6-05-proveniencia-camada-externa)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["protocolo","url"],
     "properties":{"protocolo":{"type":"string","enum":["wms","wmts","wfs","ogc_api","esri_rest","stac","geoparquet","pmtiles","postgres_fdw","s3","http","acervo"]},
       "url":{"type":"string","maxLength":2048},"credencial_id":{"type":"string","format":"uuid"},"parametros":{"type":"object"},
       "procedencia":{"type":"object","additionalProperties":true}}}'::jsonb,
   3, 'conexao', '/static/js/catalogo/tipos/conexao.js', '{}', false, 'L0-04-i')
ON CONFLICT (nome) DO UPDATE SET
  descricao      = EXCLUDED.descricao,
  esquema        = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/publicar_camada', 'item de catálogo criado a partir de uma conexão externa, com ficha de procedência lida do serviço')
ON CONFLICT (nome) DO NOTHING;
