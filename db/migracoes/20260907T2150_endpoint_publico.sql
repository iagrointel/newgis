-- 20260907T2150_endpoint_publico: catálogo de conectores públicos prontos para "um clique" (item
-- L6-02-m-catalogo-endpoints-brasil; decisão B12 do L3L6_CONCEITO). Uma linha por (tipo, url base): órgão,
-- nome, licença (vocabulário B3), origem (registro = derivado de plat.acervo_endpoint; curadoria = semente
-- app/conexao/endpoints_publicos_semente.json; fila_keyless = catálogos globais sem chave) e o resultado do
-- ÚLTIMO teste HTTP (vivo/http/content_type/ms/motivo/testado_em/falhas_seguidas). Tabela GLOBAL (não é do
-- inquilino): todo inquilino vê o mesmo catálogo; nenhum inquilino escreve nele.
--
-- Escrita só por duas funções SECURITY DEFINER (mesmo padrão de plat.conexao_saude_registrar, migração 036):
-- `endpoint_publico_semear(jsonb)` (upsert da semente + registro, chamado pelo job) e
-- `endpoint_publico_registrar(...)` (resultado de um teste). plat_app tem SELECT e EXECUTE, nunca INSERT/UPDATE.
-- "Entrada morta sai da lista e vai para 'fora do ar'": a API lista `vivo = true`; `vivo = false` é a seção
-- "fora do ar"; `vivo IS NULL` = ainda não testada (só aparece depois do primeiro teste verde).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.endpoint_publico (
  id               bigserial PRIMARY KEY,
  slug             text NOT NULL,
  orgao            text NOT NULL CHECK (btrim(orgao) <> ''),
  nome             text NOT NULL CHECK (btrim(nome) <> ''),
  tipo             text NOT NULL CHECK (tipo IN ('wms', 'wfs', 'wmts', 'esri_rest', 'stac', 'ogc_api')),
  url              text NOT NULL CHECK (url ~* '^https?://'),
  licenca          text NOT NULL DEFAULT 'nao-declarada',
  origem           text NOT NULL CHECK (origem IN ('registro', 'curadoria', 'fila_keyless')),
  fonte_id         text,                              -- acervo.fonte quando veio do registro (sem FK: só leitura)
  vivo             boolean,                           -- NULL = nunca testado
  http             int,
  content_type     text,
  ms               int,
  motivo           text,                              -- 'ok' ou a razão nomeada (html_no_lugar_do_servico, ...)
  testado_em       timestamptz,
  primeiro_ok_em   timestamptz,
  falhas_seguidas  int NOT NULL DEFAULT 0,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tipo, url)
);
CREATE INDEX IF NOT EXISTS endpoint_publico_vivo_idx ON plat.endpoint_publico (vivo, tipo, orgao);

REVOKE ALL ON plat.endpoint_publico FROM PUBLIC;
GRANT SELECT ON plat.endpoint_publico TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.endpoint_publico FROM plat_app;

CREATE OR REPLACE FUNCTION plat.endpoint_publico_semear(p_entradas jsonb) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  n int := 0;
BEGIN
  IF p_entradas IS NULL OR jsonb_typeof(p_entradas) <> 'array' THEN
    RAISE EXCEPTION 'endpoint_publico_semear: esperado um array JSON';
  END IF;
  INSERT INTO plat.endpoint_publico (slug, orgao, nome, tipo, url, licenca, origem, fonte_id)
  SELECT e->>'slug', e->>'orgao', e->>'nome', e->>'tipo', e->>'url',
         coalesce(nullif(btrim(e->>'licenca'), ''), 'nao-declarada'), e->>'origem', e->>'fonte_id'
  FROM jsonb_array_elements(p_entradas) AS e
  ON CONFLICT (tipo, url) DO UPDATE SET
    slug = EXCLUDED.slug, orgao = EXCLUDED.orgao, nome = EXCLUDED.nome, licenca = EXCLUDED.licenca,
    origem = EXCLUDED.origem, fonte_id = EXCLUDED.fonte_id, atualizado_em = now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.endpoint_publico_registrar(
  p_id bigint, p_vivo boolean, p_http int, p_content_type text, p_ms int, p_motivo text
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.endpoint_publico SET
    vivo = p_vivo, http = p_http, content_type = left(p_content_type, 200), ms = p_ms, motivo = left(p_motivo, 200),
    testado_em = now(),
    primeiro_ok_em = coalesce(primeiro_ok_em, CASE WHEN p_vivo THEN now() END),
    falhas_seguidas = CASE WHEN p_vivo THEN 0 ELSE falhas_seguidas + 1 END,
    atualizado_em = now()
  WHERE id = p_id;
END $$;

REVOKE ALL ON FUNCTION plat.endpoint_publico_semear(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.endpoint_publico_registrar(bigint, boolean, int, text, int, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.endpoint_publico_semear(jsonb) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.endpoint_publico_registrar(bigint, boolean, int, text, int, text) TO plat_app;
