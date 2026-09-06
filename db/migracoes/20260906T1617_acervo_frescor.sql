-- 20260906T1617_acervo_frescor: verificação periódica de FRESCOR das camadas do acervo da casa
-- (item L6-01-h-frescor-verificacao). Estende o registro de camadas de 027_acervo_camada.sql (L6-01-a-registro,
-- ENTREGUE) e a ficha de fonte de 021 / 040_acervo_endpoint.sql (L6-01-d-ficha-fonte, ENTREGUE).
--
-- O que esta migração cria, e por que cada peça existe:
--
--  1. `plat.acervo_frescor_execucao` — uma linha por RODADA do job semanal. Tem `tenant_id` e um índice único
--     PARCIAL por `tenant_id` enquanto `concluida_em IS NULL`: a exclusão mútua entre duas rodadas tem DIMENSÃO
--     DE INQUILINO. Isto não é preciosismo: em 06/09/2026 o item L0-05-d-periodicos foi REFUTADO porque a
--     `chave` de `plat.job` é GLOBAL (índice `ix_job_chave` da 004, sem `tenant_id`, e o despachante da 006
--     casa `r.chave = j.chave` sem olhar inquilino), então uma chave CONSTANTE deixava qualquer inquilino
--     ocupar o trinco do periódico da plataforma. Por isso o tipo de job deste item roda com `chave=None` e o
--     trinco mora AQUI, com o inquilino dentro dele.
--
--  2. `plat.acervo_camada_verificacao` — o HISTÓRICO por camada (portão: 12 verificações por camada). Guarda o
--     `COUNT(*)` EXATO, a variação contra a verificação anterior, e o estado da contagem em vocabulário fechado.
--     `linhas_exatas` é NULL quando a contagem não terminou no prazo — nunca 0 (metodologia §7.31: ausência de
--     medição não é medição; foi assim que a casa achou as duas tabelas fantasma em 01/09). `reltuples` NÃO
--     entra nesta tabela em lugar nenhum: a estimativa continua só em `plat.acervo_camada.linhas_estimadas`,
--     onde já está rotulada como estimativa.
--
--  3. `plat.acervo_endpoint_verificacao` — o resultado do teste HTTP de cada endereço, feito por NÓS, agora.
--     `acervo.endpoint` (a medição da casa, migração 040) continua SÓ LEITURA e intocada; o aviso da tela lê
--     ESTA tabela, que é da plataforma. É também o que torna a refutação do item possível sem escrever em
--     `acervo.*`: "derrubar um endpoint na fixture" é gravar aqui uma verificação que não respondeu.
--
--  4. `plat.v_acervo_camada_frescor` — a visão que a ficha e o mapa consomem: junta camada + ficha da fonte +
--     última verificação + endpoints mortos e decide `verificacao_vencida` com o MOTIVO explícito. Quatro
--     motivos, nesta ordem de prioridade: endpoint morto, prazo da fonte vencido (`proxima_verificacao` no
--     passado), nunca verificada, verificação antiga (mais de 14 dias = dois ciclos semanais perdidos).
--
--  5. Funções SECURITY DEFINER, todas exigindo `plat.tenant_atual() = plataforma` — mesmo mecanismo e mesma
--     justificativa de `plat.conexao_saude_candidatas`/`plat.conexao_saude_registrar` (036) e de
--     `plat.jobs_expurgar` (006): o job roda em UM inquilino (o técnico) e precisa contar tabelas de origem
--     que `plat_app` não pode ler. `plat.acervo_camada_contar` monta SQL dinâmico, mas o schema e a tabela vêm
--     do REGISTRO (`plat.acervo_camada`, escrito só por `scripts/acervo_sync.py` como postgres), nunca de
--     entrada de usuário, e são interpolados com `%I`.
--
-- ⛔ Esta migração NÃO escreve, não altera e não cria nada em `acervo.*`. O schema `acervo` do banco
--    `iagro_sat` é o registro da casa (376 fontes, 3.201 objetos) e é só-leitura para a plataforma.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres (dono das funções SECURITY DEFINER).

-- ---------------------------------------------------------------- 1. execução (trinco com inquilino dentro)
CREATE TABLE IF NOT EXISTS plat.acervo_frescor_execucao (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id             int NOT NULL REFERENCES plat.tenant(id),
  iniciada_em           timestamptz NOT NULL DEFAULT now(),
  concluida_em          timestamptz,
  duracao_ms            int,
  camadas_expostas      int NOT NULL DEFAULT 0,
  camadas_verificadas   int NOT NULL DEFAULT 0,
  camadas_nao_contadas  int NOT NULL DEFAULT 0,
  endpoints_testados    int NOT NULL DEFAULT 0,
  endpoints_responderam int NOT NULL DEFAULT 0,
  mudancas              int NOT NULL DEFAULT 0
);

-- trinco: no máximo UMA rodada aberta POR INQUILINO (nunca uma global que o vizinho ocupa)
CREATE UNIQUE INDEX IF NOT EXISTS ux_acervo_frescor_execucao_aberta
  ON plat.acervo_frescor_execucao (tenant_id) WHERE concluida_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_acervo_frescor_execucao_tenant
  ON plat.acervo_frescor_execucao (tenant_id, iniciada_em DESC);

-- ---------------------------------------------------------------- 2. histórico por camada
CREATE TABLE IF NOT EXISTS plat.acervo_camada_verificacao (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  acervo_camada_id   text NOT NULL REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE,
  execucao_id        bigint REFERENCES plat.acervo_frescor_execucao(id) ON DELETE SET NULL,
  verificada_em      timestamptz NOT NULL DEFAULT now(),
  contagem_estado    text NOT NULL CHECK (contagem_estado IN ('contado', 'nao_contado_no_prazo', 'erro')),
  linhas_exatas      bigint,                    -- NULL quando não contou: nunca 0 por omissão
  linhas_anteriores  bigint,
  variacao_pct       numeric(14,4),
  mudanca_relevante  boolean NOT NULL DEFAULT false,   -- |variacao_pct| > 5
  hash_estado        text NOT NULL CHECK (hash_estado IN (
                       'recalculado', 'divergente', 'sem_comando', 'nao_recalculado_tabela_grande',
                       'nao_recalculado_sem_contagem', 'erro')),
  hash_valor         text,
  hash_anterior      text,
  comando_reexecucao text,
  duracao_ms         int NOT NULL DEFAULT 0,
  CONSTRAINT ck_acervo_verificacao_contada CHECK (contagem_estado <> 'contado' OR linhas_exatas IS NOT NULL),
  CONSTRAINT ck_acervo_verificacao_nao_contada CHECK (contagem_estado = 'contado' OR linhas_exatas IS NULL)
);
CREATE INDEX IF NOT EXISTS ix_acervo_camada_verificacao_camada
  ON plat.acervo_camada_verificacao (acervo_camada_id, verificada_em DESC);
CREATE INDEX IF NOT EXISTS ix_acervo_camada_verificacao_mudanca
  ON plat.acervo_camada_verificacao (verificada_em DESC) WHERE mudanca_relevante;

-- ---------------------------------------------------------------- 3. histórico do teste HTTP por endereço
CREATE TABLE IF NOT EXISTS plat.acervo_endpoint_verificacao (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fonte_id      text NOT NULL,
  url           text NOT NULL CHECK (btrim(url) <> ''),
  execucao_id   bigint REFERENCES plat.acervo_frescor_execucao(id) ON DELETE SET NULL,
  verificada_em timestamptz NOT NULL DEFAULT now(),
  respondeu     boolean NOT NULL,
  http_status   int,
  mensagem      text,
  latencia_ms   int
);
CREATE INDEX IF NOT EXISTS ix_acervo_endpoint_verificacao_alvo
  ON plat.acervo_endpoint_verificacao (fonte_id, url, verificada_em DESC);

-- ---------------------------------------------------------------- 4. últimas verificações e a visão de frescor
CREATE OR REPLACE VIEW plat.v_acervo_camada_verificacao_ultima AS
SELECT DISTINCT ON (v.acervo_camada_id) v.*
FROM plat.acervo_camada_verificacao v
ORDER BY v.acervo_camada_id, v.verificada_em DESC, v.id DESC;

CREATE OR REPLACE VIEW plat.v_acervo_endpoint_verificacao_ultima AS
SELECT DISTINCT ON (e.fonte_id, e.url) e.*
FROM plat.acervo_endpoint_verificacao e
ORDER BY e.fonte_id, e.url, e.verificada_em DESC, e.id DESC;

-- "verificação vencida" da ficha e do mapa. 14 dias = dois ciclos semanais perdidos (o job roda domingo 05:20);
-- o número está aqui, uma vez só, e é o mesmo que a API e a tela mostram.
CREATE OR REPLACE VIEW plat.v_acervo_camada_frescor AS
WITH endpoint_por_fonte AS (
  SELECT u.fonte_id,
         count(*)::int AS endpoints_testados,
         count(*) FILTER (WHERE NOT u.respondeu)::int AS endpoints_mortos,
         max(u.verificada_em) AS endpoint_verificado_em
  FROM plat.v_acervo_endpoint_verificacao_ultima u
  GROUP BY u.fonte_id
)
SELECT
  c.acervo_camada_id,
  c.fonte_id,
  c.schema_nome,
  c.tabela,
  c.estado,
  c.linhas_estimadas,
  f.nome        AS fonte_nome,
  f.dominio     AS fonte_dominio,
  f.licenca     AS fonte_licenca,
  f.frescor     AS fonte_frescor,
  f.proxima_verificacao,
  v.verificada_em,
  v.contagem_estado,
  v.linhas_exatas,
  v.linhas_anteriores,
  v.variacao_pct,
  v.mudanca_relevante,
  v.hash_estado,
  coalesce(e.endpoints_testados, 0) AS endpoints_testados,
  coalesce(e.endpoints_mortos, 0)   AS endpoints_mortos,
  e.endpoint_verificado_em,
  (coalesce(e.endpoints_mortos, 0) > 0)                                              AS endpoint_morto,
  (f.proxima_verificacao IS NOT NULL AND f.proxima_verificacao < current_date)       AS prazo_da_fonte_vencido,
  (v.verificada_em IS NULL)                                                          AS nunca_verificada,
  (v.verificada_em IS NOT NULL AND v.verificada_em < now() - interval '14 days')     AS verificacao_antiga,
  (coalesce(e.endpoints_mortos, 0) > 0
   OR (f.proxima_verificacao IS NOT NULL AND f.proxima_verificacao < current_date)
   OR v.verificada_em IS NULL
   OR v.verificada_em < now() - interval '14 days')                                  AS verificacao_vencida,
  CASE
    WHEN coalesce(e.endpoints_mortos, 0) > 0 THEN 'endpoint_morto'
    WHEN f.proxima_verificacao IS NOT NULL AND f.proxima_verificacao < current_date THEN 'prazo_da_fonte_vencido'
    WHEN v.verificada_em IS NULL THEN 'nunca_verificada'
    WHEN v.verificada_em < now() - interval '14 days' THEN 'verificacao_antiga'
    ELSE NULL
  END AS motivo_vencida
FROM plat.acervo_camada c
LEFT JOIN plat.acervo_ficha f ON f.fonte_id = c.fonte_id
LEFT JOIN plat.v_acervo_camada_verificacao_ultima v ON v.acervo_camada_id = c.acervo_camada_id
LEFT JOIN endpoint_por_fonte e ON e.fonte_id = c.fonte_id;

-- agregado POR FONTE: é o que a ficha (`GET /api/acervo/{fonte_id}`) e o cartão da lista mostram. Uma fonte
-- está com "verificação vencida" quando QUALQUER camada exposta dela está; o motivo mostrado é o da camada de
-- maior prioridade (a ordem é a mesma da view por camada: endpoint morto > prazo da fonte > nunca verificada >
-- verificação antiga). Fonte sem camada exposta não tem estado de frescor: fica fora desta view, e a ficha
-- escreve "sem camada exposta" em vez de inventar um "em dia".
CREATE OR REPLACE VIEW plat.v_acervo_fonte_frescor AS
SELECT
  c.fonte_id,
  count(*)::int                                                   AS camadas_expostas,
  count(*) FILTER (WHERE c.verificacao_vencida)::int              AS camadas_vencidas,
  bool_or(c.verificacao_vencida)                                  AS verificacao_vencida,
  max(c.endpoints_mortos)                                         AS endpoints_mortos,
  max(c.verificada_em)                                            AS verificada_em,
  (array_remove(array_agg(c.motivo_vencida ORDER BY
     CASE c.motivo_vencida WHEN 'endpoint_morto' THEN 1 WHEN 'prazo_da_fonte_vencido' THEN 2
                           WHEN 'nunca_verificada' THEN 3 WHEN 'verificacao_antiga' THEN 4 ELSE 5 END),
   NULL))[1]                                                      AS motivo_vencida
FROM plat.v_acervo_camada_frescor c
WHERE c.estado = 'exposta'
GROUP BY c.fonte_id;

-- relatório de mudanças: contagem que variou mais de 5 % contra a verificação imediatamente anterior
CREATE OR REPLACE VIEW plat.v_acervo_frescor_mudanca AS
SELECT v.acervo_camada_id, c.fonte_id, c.schema_nome, c.tabela, v.verificada_em,
       v.linhas_anteriores, v.linhas_exatas, v.variacao_pct, v.execucao_id
FROM plat.acervo_camada_verificacao v
JOIN plat.acervo_camada c ON c.acervo_camada_id = v.acervo_camada_id
WHERE v.mudanca_relevante;

-- ---------------------------------------------------------------- 5. funções (só o inquilino técnico escreve)
CREATE OR REPLACE FUNCTION plat.acervo_frescor_exigir_plataforma() RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'verificacao de frescor do acervo so no contexto do inquilino tecnico plataforma'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
END $$;

-- abre a rodada; o índice único parcial POR INQUILINO recusa a segunda rodada aberta do MESMO inquilino
CREATE OR REPLACE FUNCTION plat.acervo_frescor_abrir() RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_id bigint; v_tenant int;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  v_tenant := plat.tenant_atual();
  BEGIN
    INSERT INTO plat.acervo_frescor_execucao(tenant_id) VALUES (v_tenant) RETURNING id INTO v_id;
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'ja existe uma rodada de frescor aberta neste inquilino' USING ERRCODE = 'lock_not_available';
  END;
  RETURN v_id;
END $$;

-- candidatas: camadas EXPOSTAS cuja última verificação venceu (ou que nunca foram verificadas), mais antigas antes
CREATE OR REPLACE FUNCTION plat.acervo_frescor_candidatas(p_intervalo interval, p_limite int)
RETURNS TABLE (acervo_camada_id text, fonte_id text, schema_nome text, tabela text,
               comando_reexecucao text, linhas_anteriores bigint, hash_anterior text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  RETURN QUERY
  SELECT c.acervo_camada_id, c.fonte_id, c.schema_nome, c.tabela, c.comando_reexecucao,
         v.linhas_exatas, v.hash_valor
  FROM plat.acervo_camada c
  LEFT JOIN plat.v_acervo_camada_verificacao_ultima v ON v.acervo_camada_id = c.acervo_camada_id
  WHERE c.estado = 'exposta'
    AND (v.verificada_em IS NULL OR v.verificada_em < now() - p_intervalo)
  ORDER BY v.verificada_em ASC NULLS FIRST, c.acervo_camada_id
  LIMIT p_limite;
END $$;

-- COUNT(*) exato da tabela de origem. O prazo NÃO é armado aqui: quem chama faz
-- `SET LOCAL statement_timeout = 25000` na MESMA transação, porque o Postgres arma o cronômetro no início do
-- comando de cliente, e um `SET` dentro da função não valeria para o próprio comando em curso (é o motivo de
-- `scripts/acervo_sync.py::_contar_exato` e do `contagem2.py` da casa fazerem os dois comandos separados).
CREATE OR REPLACE FUNCTION plat.acervo_camada_contar(p_camada_id text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_schema text; v_tabela text; v_n bigint;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  SELECT c.schema_nome, c.tabela INTO v_schema, v_tabela
  FROM plat.acervo_camada c WHERE c.acervo_camada_id = p_camada_id;
  IF v_schema IS NULL THEN
    RAISE EXCEPTION 'camada % nao esta no registro plat.acervo_camada', p_camada_id USING ERRCODE = 'no_data_found';
  END IF;
  EXECUTE format('SELECT count(*) FROM %I.%I', v_schema, v_tabela) INTO v_n;
  RETURN v_n;
END $$;

-- hash de CONTEÚDO reproduzível em SQL. NÃO é o mesmo byte-a-byte do `COPY ... | sha256sum` que a casa guarda
-- em `acervo.fonte.sha256_cmd` (a maioria daqueles comandos é um MODELO com `<schema>.<tabela>` por preencher, e
-- os executáveis são canos de shell com `sudo`, que o worker não tem e não deveria ter). O que esta função faz é
-- um hash PRÓPRIO, determinístico e declarado — soma de linhas ordenadas — comparável de uma rodada para a
-- seguinte: divergência entre duas rodadas = o conteúdo mudou. O comando que a reproduz é o próprio SQL abaixo.
CREATE OR REPLACE FUNCTION plat.acervo_camada_hash(p_camada_id text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_schema text; v_tabela text; v_hash text;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  SELECT c.schema_nome, c.tabela INTO v_schema, v_tabela
  FROM plat.acervo_camada c WHERE c.acervo_camada_id = p_camada_id;
  IF v_schema IS NULL THEN
    RAISE EXCEPTION 'camada % nao esta no registro plat.acervo_camada', p_camada_id USING ERRCODE = 'no_data_found';
  END IF;
  EXECUTE format(
    'SELECT encode(sha256(convert_to(coalesce(string_agg(linha, chr(10) ORDER BY linha), %L), %L)), %L) '
    'FROM (SELECT (t.*)::text AS linha FROM %I.%I t) s', '', 'UTF8', 'hex', v_schema, v_tabela
  ) INTO v_hash;
  RETURN v_hash;
END $$;

-- grava UMA verificação de camada e poda o histórico para as `p_manter` mais recentes (portão: 12 por camada)
CREATE OR REPLACE FUNCTION plat.acervo_frescor_registrar_camada(
  p_execucao bigint, p_camada_id text, p_contagem_estado text, p_linhas bigint,
  p_hash_estado text, p_hash text, p_comando text, p_duracao_ms int, p_manter int DEFAULT 12
) RETURNS TABLE (id bigint, variacao_pct numeric, mudanca_relevante boolean, historico int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_ant bigint; v_hash_ant text; v_var numeric; v_mud boolean; v_id bigint;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  SELECT u.linhas_exatas, u.hash_valor INTO v_ant, v_hash_ant
  FROM plat.v_acervo_camada_verificacao_ultima u WHERE u.acervo_camada_id = p_camada_id;
  -- variação só existe quando as DUAS pontas foram contadas de verdade; "não contado" nunca vira 0 nem 100 %
  IF p_linhas IS NOT NULL AND v_ant IS NOT NULL AND v_ant > 0 THEN
    v_var := round(((p_linhas - v_ant)::numeric / v_ant) * 100, 4);
  ELSIF p_linhas IS NOT NULL AND v_ant = 0 THEN
    v_var := CASE WHEN p_linhas = 0 THEN 0 ELSE NULL END;   -- de zero para n: variação percentual não existe
  ELSE
    v_var := NULL;
  END IF;
  v_mud := coalesce(abs(v_var) > 5, false);
  INSERT INTO plat.acervo_camada_verificacao(
    acervo_camada_id, execucao_id, contagem_estado, linhas_exatas, linhas_anteriores, variacao_pct,
    mudanca_relevante, hash_estado, hash_valor, hash_anterior, comando_reexecucao, duracao_ms)
  VALUES (p_camada_id, p_execucao, p_contagem_estado, p_linhas, v_ant, v_var, v_mud,
          p_hash_estado, p_hash, v_hash_ant, p_comando, coalesce(p_duracao_ms, 0))
  RETURNING plat.acervo_camada_verificacao.id INTO v_id;
  DELETE FROM plat.acervo_camada_verificacao d
  WHERE d.acervo_camada_id = p_camada_id
    AND d.id NOT IN (SELECT k.id FROM plat.acervo_camada_verificacao k
                     WHERE k.acervo_camada_id = p_camada_id
                     ORDER BY k.verificada_em DESC, k.id DESC LIMIT greatest(p_manter, 1));
  RETURN QUERY SELECT v_id, v_var, v_mud,
    (SELECT count(*)::int FROM plat.acervo_camada_verificacao k WHERE k.acervo_camada_id = p_camada_id);
END $$;

-- endereços a testar por HTTP: só os das fontes que têm camada EXPOSTA (nunca uma varredura do acervo inteiro),
-- os menos recentemente testados primeiro, no máximo `p_limite` por rodada.
CREATE OR REPLACE FUNCTION plat.acervo_frescor_endpoints(p_intervalo interval, p_limite int)
RETURNS TABLE (fonte_id text, url text, verificada_em timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  RETURN QUERY
  SELECT DISTINCT ON (e.fonte_id, e.url) e.fonte_id, e.url, u.verificada_em
  FROM plat.acervo_endpoint e
  JOIN plat.acervo_camada c ON c.fonte_id = e.fonte_id AND c.estado = 'exposta'
  LEFT JOIN plat.v_acervo_endpoint_verificacao_ultima u ON u.fonte_id = e.fonte_id AND u.url = e.url
  WHERE e.confirmado AND (u.verificada_em IS NULL OR u.verificada_em < now() - p_intervalo)
  ORDER BY e.fonte_id, e.url, u.verificada_em ASC NULLS FIRST
  LIMIT p_limite;
END $$;

CREATE OR REPLACE FUNCTION plat.acervo_frescor_registrar_endpoint(
  p_execucao bigint, p_fonte_id text, p_url text, p_respondeu boolean, p_status int,
  p_mensagem text, p_latencia_ms int, p_manter int DEFAULT 12
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_id bigint;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  INSERT INTO plat.acervo_endpoint_verificacao(
    fonte_id, url, execucao_id, respondeu, http_status, mensagem, latencia_ms)
  VALUES (p_fonte_id, p_url, p_execucao, p_respondeu, p_status, left(coalesce(p_mensagem, ''), 500), p_latencia_ms)
  RETURNING plat.acervo_endpoint_verificacao.id INTO v_id;
  DELETE FROM plat.acervo_endpoint_verificacao d
  WHERE d.fonte_id = p_fonte_id AND d.url = p_url
    AND d.id NOT IN (SELECT k.id FROM plat.acervo_endpoint_verificacao k
                     WHERE k.fonte_id = p_fonte_id AND k.url = p_url
                     ORDER BY k.verificada_em DESC, k.id DESC LIMIT greatest(p_manter, 1));
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION plat.acervo_frescor_fechar(p_execucao bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int;
BEGIN
  PERFORM plat.acervo_frescor_exigir_plataforma();
  SELECT x.tenant_id INTO v_tenant FROM plat.acervo_frescor_execucao x WHERE x.id = p_execucao;
  IF v_tenant IS NULL OR v_tenant <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'rodada % nao pertence a este inquilino', p_execucao USING ERRCODE = 'insufficient_privilege';
  END IF;
  UPDATE plat.acervo_frescor_execucao x SET
    concluida_em = now(),
    duracao_ms = (extract(epoch FROM (now() - x.iniciada_em)) * 1000)::int,
    camadas_expostas = (SELECT count(*) FROM plat.acervo_camada c WHERE c.estado = 'exposta'),
    camadas_verificadas = (SELECT count(*) FROM plat.acervo_camada_verificacao v WHERE v.execucao_id = p_execucao),
    camadas_nao_contadas = (SELECT count(*) FROM plat.acervo_camada_verificacao v
                            WHERE v.execucao_id = p_execucao AND v.contagem_estado <> 'contado'),
    endpoints_testados = (SELECT count(*) FROM plat.acervo_endpoint_verificacao e WHERE e.execucao_id = p_execucao),
    endpoints_responderam = (SELECT count(*) FROM plat.acervo_endpoint_verificacao e
                             WHERE e.execucao_id = p_execucao AND e.respondeu),
    mudancas = (SELECT count(*) FROM plat.acervo_camada_verificacao v
                WHERE v.execucao_id = p_execucao AND v.mudanca_relevante)
  WHERE x.id = p_execucao AND x.concluida_em IS NULL;
END $$;

-- ---------------------------------------------------------------- privilégios
-- plat_app LÊ tudo (registro global do acervo da casa, mesmo padrão de plat.acervo_camada da 027) e EXECUTA as
-- funções — que por dentro recusam qualquer inquilino que não seja o técnico.
REVOKE ALL ON plat.acervo_frescor_execucao, plat.acervo_camada_verificacao, plat.acervo_endpoint_verificacao
  FROM PUBLIC;
GRANT SELECT ON plat.acervo_frescor_execucao, plat.acervo_camada_verificacao, plat.acervo_endpoint_verificacao,
  plat.v_acervo_camada_verificacao_ultima, plat.v_acervo_endpoint_verificacao_ultima,
  plat.v_acervo_camada_frescor, plat.v_acervo_fonte_frescor, plat.v_acervo_frescor_mudanca TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_frescor_execucao, plat.acervo_camada_verificacao,
  plat.acervo_endpoint_verificacao FROM plat_app;

REVOKE ALL ON FUNCTION plat.acervo_frescor_exigir_plataforma() FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_abrir() FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_candidatas(interval, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_camada_contar(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_camada_hash(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_registrar_camada(bigint, text, text, bigint, text, text, text, int, int)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_endpoints(interval, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_registrar_endpoint(bigint, text, text, boolean, int, text, int, int)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.acervo_frescor_fechar(bigint) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION plat.acervo_frescor_abrir() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_frescor_candidatas(interval, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_camada_contar(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_camada_hash(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_frescor_registrar_camada(bigint, text, text, bigint, text, text, text, int, int)
  TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_frescor_endpoints(interval, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_frescor_registrar_endpoint(bigint, text, text, boolean, int, text, int, int)
  TO plat_app;
GRANT EXECUTE ON FUNCTION plat.acervo_frescor_fechar(bigint) TO plat_app;

COMMENT ON TABLE plat.acervo_camada_verificacao IS
  'Historico de verificacao de frescor por camada do acervo (item L6-01-h). linhas_exatas NULL = COUNT(*) nao '
  'concluido no prazo, nunca zero. reltuples nao entra aqui. Podado para as 12 mais recentes por camada.';
COMMENT ON TABLE plat.acervo_frescor_execucao IS
  'Uma linha por rodada do periodico acervo.frescor_verificar. O indice unico parcial por tenant_id enquanto '
  'concluida_em IS NULL e o trinco da rodada: exclusao mutua COM dimensao de inquilino (licao do L0-05-d).';
