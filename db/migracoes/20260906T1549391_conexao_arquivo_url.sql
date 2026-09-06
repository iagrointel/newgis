-- 20260906T1549391_conexao_arquivo_url: arquivo por URL pública vira camada (item L6-02-h-csv-url-geojson-kml).
--
-- Uma conexão de tipo `http` em modo `copiada` (`plat.conexao`, criada pelo L6-02-a) passa a ter um estado de
-- SINCRONIZAÇÃO: qual formato foi reconhecido, o ETag/Last-Modified/sha256 da última cópia baixada, qual item
-- de catálogo (camada_vetorial) ela alimenta, de quanto em quanto tempo reconferir e o que aconteceu na última
-- passagem. É esse estado que permite a cláusula do portão "atualização agendada detecta arquivo inalterado
-- (ETag) e não recarrega": sem ETag guardado não há requisição condicional, e sem contador de recargas não há
-- como PROVAR que não recarregou.
--
-- Uma linha por conexão (a conexão é a fonte; a camada é o destino), por isso `conexao_id` é a chave primária.
-- RLS por inquilino no mesmo molde de `plat.conexao_saude_historico` (036): plat_app só LÊ; quem escreve é a
-- função SECURITY DEFINER abaixo, que é a única chamada tanto pela rota do próprio inquilino quanto pelo
-- periódico que roda no inquilino técnico `plataforma` e cruza inquilinos.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres (dona das funções SECURITY DEFINER, que por isso
-- ignoram a RLS sem precisar de FORCE ROW LEVEL SECURITY — mesmo mecanismo de plat.jobs_expurgar, 006).
-- depende: 036_conexao_saude_e_camada.sql

CREATE TABLE IF NOT EXISTS plat.conexao_arquivo (
  conexao_id       uuid PRIMARY KEY REFERENCES plat.conexao(id) ON DELETE CASCADE,
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  formato          text,                       -- csv|geojson|kml|kmz|georss|gpx reconhecido pelos BYTES
  etag             text,                       -- ETag da última resposta 200 (vai como If-None-Match na próxima)
  last_modified    text,                       -- Last-Modified idem (If-Modified-Since)
  sha256           text,                       -- do CORPO baixado (2a defesa: servidor que ignora o condicional)
  bytes            bigint,
  item_id          uuid,                       -- plat.item da camada_vetorial que esta conexão alimenta
  importacao_id    uuid,                       -- última importação criada (plat.importacao)
  intervalo_s      int NOT NULL DEFAULT 86400 CHECK (intervalo_s >= 900 AND intervalo_s <= 2592000),
  agendado         boolean NOT NULL DEFAULT false,
  proximo_em       timestamptz,
  ultimo_em        timestamptz,
  ultimo_resultado text CHECK (ultimo_resultado IN ('carregada','nao_modificada','falhou')),
  ultimo_detalhe   text,
  sincronizacoes   int NOT NULL DEFAULT 0,     -- quantas vezes a URL foi conferida
  recargas         int NOT NULL DEFAULT 0,     -- quantas dessas viraram carga de verdade (o resto foi 304/sha igual)
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conexao_arquivo_tenant ON plat.conexao_arquivo (tenant_id);
CREATE INDEX IF NOT EXISTS ix_conexao_arquivo_proximo ON plat.conexao_arquivo (proximo_em) WHERE agendado;

ALTER TABLE plat.conexao_arquivo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_conexao_arquivo_ler ON plat.conexao_arquivo;
CREATE POLICY p_conexao_arquivo_ler ON plat.conexao_arquivo FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

REVOKE ALL ON plat.conexao_arquivo FROM PUBLIC;
GRANT SELECT ON plat.conexao_arquivo TO plat_app;

-- ---------------------------------------------------------------- configurar (cria/edita o agendamento)
-- Chamada pela rota do PRÓPRIO inquilino (POST /api/conexoes/{id}/arquivo). Só mexe em conexão do inquilino
-- corrente: a checagem é explícita aqui porque a função é SECURITY DEFINER e portanto ignora a RLS.
CREATE OR REPLACE FUNCTION plat.conexao_arquivo_configurar(
  p_conexao_id uuid, p_intervalo_s int, p_agendado boolean
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int;
BEGIN
  SELECT tenant_id INTO v_tenant FROM plat.conexao WHERE id = p_conexao_id;
  IF v_tenant IS NULL OR v_tenant IS DISTINCT FROM plat.tenant_atual() THEN
    RAISE EXCEPTION 'conexao inexistente neste inquilino' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO plat.conexao_arquivo(conexao_id, tenant_id, intervalo_s, agendado, proximo_em)
  VALUES (p_conexao_id, v_tenant, p_intervalo_s, p_agendado,
          CASE WHEN p_agendado THEN now() ELSE NULL END)
  ON CONFLICT (conexao_id) DO UPDATE SET
    intervalo_s   = EXCLUDED.intervalo_s,
    agendado      = EXCLUDED.agendado,
    proximo_em    = CASE WHEN EXCLUDED.agendado THEN coalesce(plat.conexao_arquivo.proximo_em, now()) ELSE NULL END,
    atualizado_em = now();
END $$;

-- ---------------------------------------------------------------- candidatas do periódico (cruza inquilinos)
CREATE OR REPLACE FUNCTION plat.conexao_arquivo_candidatas(p_limite int)
RETURNS TABLE (conexao_id uuid, tenant_id int, dono_id int, url text, credencial_cifrada text, etag text,
               last_modified text, sha256 text, item_id uuid, intervalo_s int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'sincronizacao de arquivo por URL so no contexto do inquilino tecnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN QUERY
  SELECT a.conexao_id, a.tenant_id, c.dono_id, c.url, c.credencial_cifrada, a.etag, a.last_modified, a.sha256,
         a.item_id, a.intervalo_s
  FROM plat.conexao_arquivo a
  JOIN plat.conexao c ON c.id = a.conexao_id
  WHERE a.agendado AND (a.proximo_em IS NULL OR a.proximo_em <= now())
  ORDER BY a.proximo_em ASC NULLS FIRST
  LIMIT p_limite;
END $$;

-- ---------------------------------------------------------------- registra o resultado de UMA sincronização
-- `p_recarregou` separa as duas coisas que o portão exige distinguir: conferir a URL (sempre incrementa
-- `sincronizacoes`) e recarregar de verdade (só então incrementa `recargas` e troca etag/sha256/item_id).
-- Quando o resultado é 'nao_modificada', etag/last_modified são ATUALIZADOS se o servidor mandou valores novos
-- (um 304 pode trazer ETag novo) mas o sha256 e o item_id ficam como estavam — nada foi carregado.
CREATE OR REPLACE FUNCTION plat.conexao_arquivo_registrar(
  p_conexao_id uuid, p_resultado text, p_detalhe text, p_recarregou boolean,
  p_formato text DEFAULT NULL, p_etag text DEFAULT NULL, p_last_modified text DEFAULT NULL,
  p_sha256 text DEFAULT NULL, p_bytes bigint DEFAULT NULL, p_item_id uuid DEFAULT NULL,
  p_importacao_id uuid DEFAULT NULL
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int; v_atual int; v_intervalo int;
BEGIN
  SELECT a.tenant_id, a.intervalo_s INTO v_tenant, v_intervalo FROM plat.conexao_arquivo a WHERE a.conexao_id = p_conexao_id;
  IF v_tenant IS NULL THEN
    RETURN; -- a conexão foi apagada entre a candidatura e o registro: nunca erro (mesma regra da saúde, 036)
  END IF;
  v_atual := plat.tenant_atual();
  IF v_atual IS DISTINCT FROM v_tenant
     AND v_atual IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'sem permissao para registrar a sincronizacao desta conexao' USING ERRCODE = 'insufficient_privilege';
  END IF;
  UPDATE plat.conexao_arquivo SET
    ultimo_resultado = p_resultado,
    ultimo_detalhe   = left(coalesce(p_detalhe, ''), 2000),
    ultimo_em        = now(),
    sincronizacoes   = sincronizacoes + 1,
    recargas         = recargas + CASE WHEN p_recarregou THEN 1 ELSE 0 END,
    formato          = coalesce(p_formato, formato),
    etag             = coalesce(p_etag, etag),
    last_modified    = coalesce(p_last_modified, last_modified),
    sha256           = CASE WHEN p_recarregou THEN coalesce(p_sha256, sha256) ELSE sha256 END,
    bytes            = CASE WHEN p_recarregou THEN coalesce(p_bytes, bytes) ELSE bytes END,
    item_id          = CASE WHEN p_recarregou THEN coalesce(p_item_id, item_id) ELSE item_id END,
    importacao_id    = coalesce(p_importacao_id, importacao_id),
    proximo_em       = CASE WHEN agendado THEN now() + make_interval(secs => v_intervalo) ELSE NULL END,
    atualizado_em    = now()
  WHERE conexao_id = p_conexao_id;
END $$;

REVOKE ALL ON FUNCTION plat.conexao_arquivo_configurar(uuid, int, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.conexao_arquivo_candidatas(int) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.conexao_arquivo_registrar(uuid, text, text, boolean, text, text, text, text, bigint, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.conexao_arquivo_configurar(uuid, int, boolean) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.conexao_arquivo_candidatas(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.conexao_arquivo_registrar(uuid, text, text, boolean, text, text, text, text, bigint, uuid, uuid) TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/sincronizar_arquivo', 'sincronização de arquivo por URL pública (CSV/GeoJSON/KML/KMZ/GeoRSS/GPX) pedida numa conexão')
ON CONFLICT (nome) DO NOTHING;
