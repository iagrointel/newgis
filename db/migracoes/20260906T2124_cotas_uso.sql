-- 20260906T2124_cotas_uso (item L0-07-c-cotas-uso): medição diária de uso por inquilino (série
-- plat.uso_inquilino) e as peças de banco das cotas que faltavam. O que JÁ existia e NÃO é recriado aqui:
-- tenant.cota_bytes (002), tenant.uso_bytes/uso_reservado_bytes da cota de TABELA (029), plat.cota_itens (011),
-- plat.cota_jobs_dia (004), plat.cota_usuarios/plat.usuarios_ativos (034) e a reserva atômica do upload
-- retomável (046, SELECT ... FOR UPDATE na linha do tenant). Esta migração acrescenta:
--   1. plat.arquivo_uso_bytes(tenant): soma dos bytes VIVOS de plat.arquivo — base lógica da cota de objetos,
--      consultada sob o mesmo FOR UPDATE do tenant em app/objetos.py::guardar (refutação: 20 uploads
--      paralelos; sem contador novo que possa dessincronizar, mesmo princípio da 046).
--   2. plat.uso_bytes_banco(tenant): soma de pg_total_relation_size das tabelas d_<slug> do inquilino —
--      fórmula ÚNICA, usada pela medição diária e pela tela (a cláusula "medição bate com
--      pg_total_relation_size (diferença <= 1%)" compara exatamente esta fórmula).
--   3. plat.uso_inquilino: série diária (um ponto por inquilino por dia).
--   4. plat.uso_medir(tenant, dia, bytes_bucket): upsert de um ponto da série; o bytes do bucket vem de fora
--      (Admin API do Garage é chamada HTTP, não cabe em SQL). Aproveita e reconcilia tenant.uso_bytes com o
--      tamanho físico medido quando não há carga em andamento (o contador transacional cobre o tempo real; a
--      medição diária corrige o desvio — item na lixeira continua contando porque a tabela d_<slug> só cai no
--      expurgo, que é o que a refutação "apaga item para liberar cota" exige).
--   5. plat.uso_buckets_listar(): (tenant_id, bucket_id) de todos os inquilinos, para o periódico medir o
--      bucket de cada um pela Admin API (SECURITY DEFINER: plat_worker não lê plat.arquivo_bucket de outro
--      inquilino pela RLS).
--   6. plat.tenant_cotas_definir(...): superadmin altera cota_bytes (coluna) e cota_usuarios/cota_itens/
--      cota_jobs_dia (chaves de tenant.config que as funções de cota já leem AO VIVO — efeito imediato por
--      construção, sem cache). Superadmin resolvido pela sessão (hash), mesmo padrão de plat.tenant_suspender.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- ---------------------------------------------------------------- 1. uso lógico de objetos (bytes vivos)
CREATE OR REPLACE FUNCTION plat.arquivo_uso_bytes(p_tenant int) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce(sum(bytes), 0)::bigint FROM plat.arquivo WHERE tenant_id = p_tenant AND apagado_em IS NULL
$$;

-- ---------------------------------------------------------------- 2. uso físico de tabelas d_<slug>
-- (fórmula única da cláusula de 1%: tabelas comuns e materializadas do schema d_<slug>; pg_total_relation_size
-- já inclui índices e TOAST de cada uma. Tabela particionada ('p') não tem armazenamento próprio.)
CREATE OR REPLACE FUNCTION plat.uso_bytes_banco(p_tenant int) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0)::bigint
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN plat.tenant t ON t.id = p_tenant
  WHERE n.nspname = 'd_' || t.slug AND c.relkind IN ('r', 'm')
$$;

-- ---------------------------------------------------------------- 3. série diária
CREATE TABLE IF NOT EXISTS plat.uso_inquilino (
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  dia                 date NOT NULL,
  bytes_banco         bigint NOT NULL DEFAULT 0,    -- plat.uso_bytes_banco no momento da medição
  bytes_bucket        bigint,                        -- Admin API do Garage; NULL = não medido (sem bucket/Garage fora)
  itens               int NOT NULL DEFAULT 0,        -- itens vivos no fim do dia medido
  itens_lixeira       int NOT NULL DEFAULT 0,        -- na lixeira (contam na cota até o expurgo)
  usuarios_ativos_30d int NOT NULL DEFAULT 0,        -- usuários distintos em log_acesso nos 30 dias até o dia
  jobs                int NOT NULL DEFAULT 0,        -- jobs criados no dia (UTC)
  job_tempo_ms        bigint NOT NULL DEFAULT 0,     -- soma da duração (terminado_em - iniciado_em) dos jobs
                                                     -- terminados no dia; tempo de parede, não CPU de processo
                                                     -- (plat.job não tem contador de CPU — declarado no handoff)
  requisicoes         bigint NOT NULL DEFAULT 0,     -- linhas de log_acesso do inquilino no dia
  bytes_servidos      bigint NOT NULL DEFAULT 0,     -- soma de log_acesso.bytes no dia
  medido_em           timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, dia)
);
ALTER TABLE plat.uso_inquilino ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_uso_inquilino ON plat.uso_inquilino;
CREATE POLICY p_uso_inquilino ON plat.uso_inquilino FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
REVOKE INSERT, UPDATE, DELETE ON plat.uso_inquilino FROM plat_app;
GRANT SELECT ON plat.uso_inquilino TO plat_app;

-- ---------------------------------------------------------------- 4. medição de um ponto
-- p_bytes_bucket: medido pela Admin API do Garage no job periódico (chamada HTTP não cabe aqui); NULL deixa a
-- coluna anterior intacta (COALESCE) — um dia com o Garage fora do ar NÃO apaga a medição anterior.
CREATE OR REPLACE FUNCTION plat.uso_medir(p_tenant int, p_dia date, p_bytes_bucket bigint DEFAULT NULL)
RETURNS SETOF plat.uso_inquilino
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  v_banco bigint; v_itens int; v_lixeira int; v_ativos int; v_jobs int; v_tempo bigint; v_req bigint; v_bytes bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  v_banco := plat.uso_bytes_banco(p_tenant);
  SELECT count(*) FILTER (WHERE apagado_em IS NULL), count(*) FILTER (WHERE apagado_em IS NOT NULL)
    INTO v_itens, v_lixeira FROM plat.item WHERE tenant_id = p_tenant;
  SELECT count(DISTINCT usuario_id) INTO v_ativos
  FROM plat.log_acesso
  WHERE tenant_id = p_tenant AND usuario_id IS NOT NULL
    AND em >= (p_dia - 29)::timestamptz AND em < (p_dia + 1)::timestamptz;
  SELECT count(*) INTO v_jobs
  FROM plat.job
  WHERE tenant_id = p_tenant AND criado_em >= p_dia::timestamptz AND criado_em < (p_dia + 1)::timestamptz;
  SELECT coalesce(sum(EXTRACT(EPOCH FROM (terminado_em - iniciado_em)) * 1000), 0)::bigint INTO v_tempo
  FROM plat.job
  WHERE tenant_id = p_tenant AND terminado_em IS NOT NULL AND iniciado_em IS NOT NULL
    AND terminado_em >= p_dia::timestamptz AND terminado_em < (p_dia + 1)::timestamptz;
  SELECT count(*), coalesce(sum(bytes), 0)::bigint INTO v_req, v_bytes
  FROM plat.log_acesso
  WHERE tenant_id = p_tenant AND em >= p_dia::timestamptz AND em < (p_dia + 1)::timestamptz;
  INSERT INTO plat.uso_inquilino AS u
    (tenant_id, dia, bytes_banco, bytes_bucket, itens, itens_lixeira, usuarios_ativos_30d, jobs, job_tempo_ms,
     requisicoes, bytes_servidos, medido_em)
  VALUES
    (p_tenant, p_dia, v_banco, p_bytes_bucket, v_itens, v_lixeira, v_ativos, v_jobs, v_tempo, v_req, v_bytes, now())
  ON CONFLICT (tenant_id, dia) DO UPDATE SET
    bytes_banco = EXCLUDED.bytes_banco,
    bytes_bucket = coalesce(EXCLUDED.bytes_bucket, u.bytes_bucket),
    itens = EXCLUDED.itens, itens_lixeira = EXCLUDED.itens_lixeira,
    usuarios_ativos_30d = EXCLUDED.usuarios_ativos_30d,
    jobs = EXCLUDED.jobs, job_tempo_ms = EXCLUDED.job_tempo_ms,
    requisicoes = EXCLUDED.requisicoes, bytes_servidos = EXCLUDED.bytes_servidos,
    medido_em = EXCLUDED.medido_em;
  -- reconciliação do contador transacional de tabelas com o tamanho físico medido; nunca durante uma carga
  -- (a 029 reserva em uso_reservado_bytes e acerta uso_bytes no fim — mexer no meio cobraria duas vezes)
  UPDATE plat.tenant SET uso_bytes = v_banco
  WHERE id = p_tenant AND uso_bytes IS DISTINCT FROM v_banco
    AND NOT EXISTS (SELECT 1 FROM plat.importacao WHERE tenant_id = p_tenant
                    AND estado IN ('confirmada', 'carregando'));
  RETURN QUERY SELECT * FROM plat.uso_inquilino WHERE tenant_id = p_tenant AND dia = p_dia;
END $$;

-- ---------------------------------------------------------------- 5. buckets de todos os inquilinos (para o
-- periódico medir bytes pela Admin API; sem segredo de chave — só o id, o resto fica em app/objetos.py)
CREATE OR REPLACE FUNCTION plat.uso_buckets_listar()
RETURNS TABLE (tenant_id int, bucket_id text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id FROM plat.arquivo_bucket b
  JOIN plat.tenant t ON t.id = b.tenant_id WHERE t.ativo
$$;

-- ---------------------------------------------------------------- 6. cotas pelo superadmin (efeito imediato:
-- as funções plat.cota_* leem a linha/config do tenant AO VIVO em cada requisição; a cota do bucket Garage é
-- ressincronizada pela rota logo depois, app/auth/rotas_plataforma.py). NULL = não mexe naquela cota.
CREATE OR REPLACE FUNCTION plat.tenant_cotas_definir(
  p_sessao_hash text, p_tenant int, p_cota_bytes bigint DEFAULT NULL,
  p_cota_usuarios int DEFAULT NULL, p_cota_itens int DEFAULT NULL, p_cota_jobs_dia int DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_config jsonb := '{}'::jsonb;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  IF p_cota_bytes IS NOT NULL AND p_cota_bytes < 104857600 THEN  -- mesmo piso de ORG_COTA_BYTES_MIN (100 MiB)
    RAISE EXCEPTION 'cota_bytes_abaixo_do_minimo';
  END IF;
  IF p_cota_usuarios IS NOT NULL THEN
    IF p_cota_usuarios < 1 THEN RAISE EXCEPTION 'cota_usuarios_abaixo_do_minimo'; END IF;
    v_config := v_config || jsonb_build_object('cota_usuarios', p_cota_usuarios);
  END IF;
  IF p_cota_itens IS NOT NULL THEN
    IF p_cota_itens < 1 THEN RAISE EXCEPTION 'cota_itens_abaixo_do_minimo'; END IF;
    v_config := v_config || jsonb_build_object('catalogo', jsonb_build_object('cota_itens', p_cota_itens));
  END IF;
  IF p_cota_jobs_dia IS NOT NULL THEN
    IF p_cota_jobs_dia < 0 THEN RAISE EXCEPTION 'cota_jobs_dia_invalida'; END IF;
    v_config := v_config || jsonb_build_object('cota_jobs_dia', p_cota_jobs_dia);
  END IF;
  UPDATE plat.tenant
  SET cota_bytes = coalesce(p_cota_bytes, cota_bytes), config = config || v_config
  WHERE id = p_tenant;
END $$;

-- ---------------------------------------------------------------- permissões (regra da 006/013: explícito por
-- função, nunca ON ALL; plat_worker só nas duas que o periódico jobs.uso_medir chama)
REVOKE EXECUTE ON FUNCTION plat.arquivo_uso_bytes(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.uso_bytes_banco(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.uso_medir(int, date, bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.uso_buckets_listar() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_cotas_definir(text, int, bigint, int, int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.arquivo_uso_bytes(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.uso_bytes_banco(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.uso_medir(int, date, bigint) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.uso_medir(int, date, bigint) TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.uso_buckets_listar() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.uso_buckets_listar() TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.tenant_cotas_definir(text, int, bigint, int, int, int) TO plat_app;
