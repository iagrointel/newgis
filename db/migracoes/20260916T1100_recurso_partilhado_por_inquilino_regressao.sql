-- depende: 20260906T2110_jobs_justica_inquilino.sql
-- depende: 20260908T2210_camada_schema_garantir_serializa.sql
--
-- Conserto de regressão de fusão (tests/unit/test_recurso_partilhado_por_inquilino.py, achado do laudo
-- g3 de 06/09/2026): duas famílias de função foram redefinidas mais de uma vez em migrações paralelas
-- que nasceram do MESMO estado anterior e nunca se enxergaram — cada `CREATE OR REPLACE` seguinte apagou
-- a defesa por inquilino que uma migração irmã tinha acrescentado.
--
-- 1. plat.job_pegar: a 20260906T1615a3f (item L0-05-a/recurso-partilhado-por-inquilino) tornou o trinco
--    por `chave` restrito ao MESMO inquilino (r.tenant_id = j.tenant_id — sem isso, dois inquilinos com
--    a mesma chave de job se travavam um ao outro) e repartiu a escolha por inquilino antes da
--    prioridade. A 20260906T2109 (modo de manutenção) e a 20260906T2110 (item L0-05-e-justica-entre-
--    inquilinos, rodízio por `max(iniciado_em)`) cada uma redefiniu a função de novo a partir do estado
--    ANTERIOR a 1615a3f: a 2109 acrescentou o filtro de manutenção mas perdeu o trinco por inquilino e a
--    repartição; a 2110 refinou o rodízio (turno por último início, mais forte que o rodízio simples da
--    1615a3f — cota comprovada em tests/api/jobs/test_jobs_justica.py) mas também perdeu o trinco por
--    inquilino e o filtro de manutenção. Esta migração funde as três: rodízio por turno (2110) + trinco
--    por inquilino (1615a3f) + filtro de manutenção com exceção somente_leitura (2109).
-- 2. plat.camada_schema_garantir: a 20260908T2210 (trava de transação contra "tuple concurrently
--    updated") foi escrita sobre a versão anterior a 20260907T0245/1615a3f, que introduziu
--    `plat.camada_schema_prefixo()` para que produção, homologação e cada trilha do laço escrevam em
--    schemas de dado diferentes — sem o prefixo, toda instalação volta a escrever em `d_<slug>` e uma
--    trilha enxerga/derruba o dado de outra. A 20260911T1440 conserta isto em TEMPO DE EXECUÇÃO
--    (reescreve qualquer função viva que ainda concatene o prefixo velho à mão), mas não muda o texto
--    guardado nas migrações — e é o texto que este teste (e qualquer leitura futura das migrações, sem
--    banco) confere. Aqui a função volta a ser escrita, de forma estável, com o prefixo de instalação E
--    com a trava de transação da 2210, as duas juntas.

CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
  WITH aptos AS (                       -- inquilinos com job pronto a rodar (só destes o turno interessa)
    SELECT DISTINCT j.tenant_id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.somente_leitura OR NOT plat.modo_bloqueia(j.tenant_id))
  ),
  turno AS (                            -- última vez que cada inquilino apto foi atendido
    SELECT j.tenant_id, max(j.iniciado_em) AS ultimo_inicio
    FROM plat.job j JOIN aptos a ON a.tenant_id = j.tenant_id
    WHERE j.iniciado_em IS NOT NULL
    GROUP BY j.tenant_id
  ),
  c AS (
    SELECT j.id FROM plat.job j
    LEFT JOIN turno t ON j.tenant_id = t.tenant_id
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.somente_leitura OR NOT plat.modo_bloqueia(j.tenant_id))
      -- o trinco é do INQUILINO: mesma chave em inquilinos diferentes não se estorva (achado g3)
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r
             WHERE r.chave = j.chave AND r.tenant_id = j.tenant_id AND r.estado = 'rodando'))
      AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
          < plat.cota_jobs_simultaneos(j.tenant_id)
    ORDER BY t.ultimo_inicio ASC NULLS FIRST, j.prioridade, j.agendado_para, j.criado_em
    FOR UPDATE OF j SKIP LOCKED LIMIT 1)
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = tentativa + 1, progresso = 0, mensagem = NULL
  FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('plat:camada_schema_garantir:' || p_slug)::bigint);
  -- prefixo de instalação: sem ele produção, homologação e as trilhas partilhariam o mesmo d_<slug>
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', plat.camada_schema_prefixo() || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', plat.camada_schema_prefixo() || p_slug);
END $$;
