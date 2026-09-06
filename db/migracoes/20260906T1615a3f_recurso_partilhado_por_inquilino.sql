-- 20260906T1615a3f_recurso_partilhado_por_inquilino
--
-- Conserto de CLASSE, não de item: cinco adversários independentes (laudos ataque-g2/g3/g4/g6 de 06/09)
-- mediram o mesmo padrão. O que é POR LINHA está protegido (RLS, filtro de dono, contexto por inquilino:
-- atacado, aguentou). O que é RECURSO PARTILHADO não tinha dimensão de inquilino nenhuma. Esta migração
-- acrescenta essa dimensão nos pontos de banco; app/jobs/eventos.py faz o mesmo no orçamento de conexões.
--
--  1. chave do trinco (plat.job_pegar): a comparação `r.chave = j.chave` não olhava tenant_id, então um
--     inquilino congelava o trabalho de outro. MEDIDO no laudo g3: inquilino 2 parado por chave do 1.
--     Passa a ser (tenant_id, chave). Além disso, o espaço de nome `sys:` fica reservado a trabalho
--     nascido de agenda (os periódicos da plataforma), fora do alcance de /api/jobs.
--  2. justiça da fila: a ordenação era global (prioridade, agendado_para, criado_em) e a prioridade 1..9
--     é livre a qualquer usuário. MEDIDO: quem chegou primeiro foi servido em 21º. Passa a repartir por
--     inquilino: entre inquilinos vale quem tem menos trabalho rodando e depois quem espera há mais tempo;
--     dentro do inquilino a prioridade escolhida pelo usuário continua valendo.
--  3. ceifa sem executor vivo (plat.job_ceifar_vencidos): plat.job_ceifar só era chamada de dentro do laço
--     do worker e só plat_worker tinha EXECUTE; com o worker morto ninguém ceifava e a tela mostrava
--     execução que não existia (MEDIDO: 68 s depois do SIGKILL o trabalho seguia `rodando`). A função nova
--     é do plat_app, ceifa SÓ o inquilino do contexto (nunca conta nem devolve trabalho de outro) e tem
--     piso de 60 s no limite de sinal.
--  4. morte do executor = tentativa, não reinício: três mortes seguidas terminavam em `concluido` porque a
--     ceifa devolvia com p_conta_tentativa := false e o teto de reinícios é 5. A refutação escrita do
--     L0-05-a exige `falhou` na quarta passagem e nunca `concluido`. Com max_tentativas = 3 (padrão da 004)
--     a terceira morte fecha em `falhou`. `reinicios` continua contando o que NÃO é culpa do trabalho:
--     parada limpa do worker (systemctl restart), que segue com p_conta_tentativa := false.
--  5. contador de cota que só sobe: plat.tenant.uso_bytes era somado em app/ingestao/carregar.py e nunca
--     devolvido (MEDIDO: 188.416 -> 376.832 -> 376.832 depois de apagar e expurgar). A contabilidade sai
--     do código de aplicação e vira gatilho em plat.item, simétrico por construção, mais uma reconciliação
--     única que zera a diferença acumulada.
--  6. schema de dado sem prefixo de instalação: 'd_' || slug fazia produção, homologação e as quinze
--     trilhas deste laço partilharem d_demo, e a segunda instalação não importava nada
--     (permission denied for schema d_demo, medido ao vivo). O prefixo passa a incluir a instalação.
--
-- Idempotente, sem BEGIN/COMMIT. Arquivos aplicados (004/006/008/012/029) não são editados: tudo aqui é
-- CREATE OR REPLACE em arquivo novo, como manda o ADR 0014.

-- ================================================================ 1. chave do trinco + 2. justiça da fila
CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job; t record;
BEGIN
  PERFORM plat.via_worker_ligar();
  -- repartição por inquilino: a volta externa ordena os INQUILINOS que têm trabalho elegível (menos
  -- trabalho rodando primeiro, depois quem espera há mais tempo); a interna escolhe o trabalho DENTRO do
  -- inquilino pela prioridade que o usuário daquele inquilino pediu. Prioridade não atravessa inquilino.
  FOR t IN
    SELECT j.tenant_id,
           (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando') AS rodando,
           min(j.criado_em) AS espera_desde
      FROM plat.job j
     WHERE j.estado = 'pendente' AND j.agendado_para <= now() AND (p_pesado_ok OR NOT j.pesado)
     GROUP BY j.tenant_id
     ORDER BY 2, 3, 1
  LOOP
    WITH c AS (
      SELECT j.id FROM plat.job j
       WHERE j.estado = 'pendente' AND j.agendado_para <= now() AND j.tenant_id = t.tenant_id
         AND (p_pesado_ok OR NOT j.pesado)
         -- o trinco é do INQUILINO: mesma chave em inquilinos diferentes não se estorva (achado g3)
         AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r
                WHERE r.chave = j.chave AND r.tenant_id = j.tenant_id AND r.estado = 'rodando'))
         AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
             < plat.cota_jobs_simultaneos(j.tenant_id)
       ORDER BY j.prioridade, j.agendado_para, j.criado_em
       FOR UPDATE OF j SKIP LOCKED LIMIT 1)
    UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                        tentativa = tentativa + 1, progresso = 0, mensagem = NULL
    FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
    EXIT WHEN pego.id IS NOT NULL;
  END LOOP;
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;

-- índice que a volta externa usa (a fila só olha pendente e agendado_para; sem isto o GROUP BY varre a
-- tabela inteira, que a medida de 100 mil trabalhos do laudo g3 mostrou ser grande)
CREATE INDEX IF NOT EXISTS job_pendente_ix ON plat.job (tenant_id, prioridade, agendado_para, criado_em)
  WHERE estado = 'pendente';

-- espaço de nome reservado: `sys:` só em trabalho nascido de agenda (é assim que os periódicos da
-- plataforma entram). Sem isto, um usuário com perfil de editor de qualquer inquilino escolhia a chave
-- constante do periódico e travava o expurgo de sessões vencidas (achado g3 no L0-05-d).
CREATE OR REPLACE FUNCTION plat.job_chave_reservada() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.chave IS NOT NULL AND NEW.chave LIKE 'sys:%' AND NEW.agenda_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = NEW.tenant_id AND t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'chave % é do espaço reservado da plataforma (sys:)', NEW.chave
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
REVOKE EXECUTE ON FUNCTION plat.job_chave_reservada() FROM PUBLIC, plat_app;
DROP TRIGGER IF EXISTS job_chave_reservada ON plat.job;
CREATE TRIGGER job_chave_reservada BEFORE INSERT ON plat.job
  FOR EACH ROW EXECUTE FUNCTION plat.job_chave_reservada();

-- ================================================================ 3. e 4. ceifa
-- morte do executor passa a consumir TENTATIVA (p_conta_tentativa := true). `reinicios` fica só para a
-- parada limpa do worker, que não é culpa do trabalho (app/jobs/worker.py::_parar segue com false).
CREATE OR REPLACE FUNCTION plat.job_ceifar(p_limite_s int, p_max_reinicios int DEFAULT 5) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT j.id, j.worker FROM plat.job j
           WHERE j.estado = 'rodando'
             AND coalesce(j.heartbeat_em, j.iniciado_em) < now() - make_interval(secs => p_limite_s)
             AND NOT EXISTS (SELECT 1 FROM plat.worker w WHERE w.nome = j.worker
                             AND w.heartbeat_em >= now() - make_interval(secs => p_limite_s)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker morreu sem terminar o trabalho', true, 0, p_max_reinicios);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.job_ceifar(int, int) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.job_ceifar(int, int) TO plat_worker;

-- ceifa que a API chama quando nenhum executor está vivo. Só o inquilino do contexto: não conta, não
-- devolve e não revela trabalho de outro inquilino. Piso de 60 s para que ninguém use isto como
-- cancelamento em massa do próprio inquilino.
CREATE OR REPLACE FUNCTION plat.job_ceifar_vencidos(p_limite_s int DEFAULT 60) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; t int; lim int := greatest(coalesce(p_limite_s, 60), 60);
BEGIN
  t := plat.tenant_atual();
  IF t IS NULL THEN RAISE EXCEPTION 'sem_tenant_no_contexto'; END IF;
  FOR r IN SELECT j.id, j.worker FROM plat.job j
           WHERE j.estado = 'rodando' AND j.tenant_id = t
             AND coalesce(j.heartbeat_em, j.iniciado_em) < now() - make_interval(secs => lim)
             AND NOT EXISTS (SELECT 1 FROM plat.worker w WHERE w.nome = j.worker
                             AND w.heartbeat_em >= now() - make_interval(secs => lim)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker morreu sem terminar o trabalho', true, 0, 5);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.job_ceifar_vencidos(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.job_ceifar_vencidos(int) TO plat_app, plat_worker;

-- ================================================================ 5. contador de cota que desce
CREATE OR REPLACE FUNCTION plat.item_uso_bytes() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE antes bigint := 0; depois bigint := 0;
BEGIN
  IF TG_OP <> 'INSERT' AND OLD.tipo = 'camada_vetorial' THEN antes := coalesce(OLD.tamanho_bytes, 0); END IF;
  IF TG_OP <> 'DELETE' AND NEW.tipo = 'camada_vetorial' THEN depois := coalesce(NEW.tamanho_bytes, 0); END IF;
  IF antes <> depois THEN
    UPDATE plat.tenant SET uso_bytes = greatest(0, uso_bytes - antes + depois)
     WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
REVOKE EXECUTE ON FUNCTION plat.item_uso_bytes() FROM PUBLIC, plat_app;
DROP TRIGGER IF EXISTS item_uso_bytes ON plat.item;
CREATE TRIGGER item_uso_bytes AFTER INSERT OR DELETE OR UPDATE OF tamanho_bytes, tipo, tenant_id ON plat.item
  FOR EACH ROW EXECUTE FUNCTION plat.item_uso_bytes();

-- reconciliação única: apaga a diferença que a soma sem devolução acumulou até aqui
UPDATE plat.tenant t SET uso_bytes = coalesce(
  (SELECT sum(i.tamanho_bytes) FROM plat.item i WHERE i.tenant_id = t.id AND i.tipo = 'camada_vetorial'), 0)
WHERE t.uso_bytes IS DISTINCT FROM coalesce(
  (SELECT sum(i.tamanho_bytes) FROM plat.item i WHERE i.tenant_id = t.id AND i.tipo = 'camada_vetorial'), 0);

-- ================================================================ 6. schema de dado por instalação
-- O prefixo é 'd_' + o nome do schema desta instalação + '_'. Em produção dá d_plat_<slug>; na trilha
-- `partilha` dá d_plat_tpartilha_<slug>. O literal é resolvido AQUI, na aplicação da migração (o
-- reescritor de instalação troca 'plat' pelo schema desta instalação), e fica gravado no corpo da função
-- — é o que torna a diferença entre duas instalações verificável por pg_get_functiondef.
DO $do$
BEGIN
  EXECUTE format(
    $f$CREATE OR REPLACE FUNCTION plat.camada_schema_prefixo() RETURNS text
       LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$ SELECT %L::text $fn$ $f$,
    'd_' || 'plat' || '_');

  EXECUTE format($f$
CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $fn$
BEGIN
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  -- prefixo de instalação (%s): sem ele produção, homologação e as trilhas partilhariam o mesmo d_<slug>
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %%I AUTHORIZATION plat_app', %L || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %%I TO plat_leitor', %L || p_slug);
END $fn$ $f$, 'd_' || 'plat' || '_', 'd_' || 'plat' || '_', 'd_' || 'plat' || '_');
END $do$;
GRANT EXECUTE ON FUNCTION plat.camada_schema_prefixo() TO plat_app, plat_leitor, plat_worker;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;

-- camada_preparar: mesma função da 029, com a conferência de dono do schema passando pelo prefixo
CREATE OR REPLACE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text, p_usuario int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND plat.camada_schema_prefixo() || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  nome_curto := substr(p_tabela, 3);

  EXECUTE format(
    'ALTER TABLE %1$I.%2$I '
    '  ADD COLUMN IF NOT EXISTS globalid       uuid        NOT NULL DEFAULT gen_random_uuid(), '
    '  ADD COLUMN IF NOT EXISTS versao         int         NOT NULL DEFAULT 1, '
    '  ADD COLUMN IF NOT EXISTS tenant_id      int         NOT NULL DEFAULT %3$L, '
    '  ADD COLUMN IF NOT EXISTS criado_em      timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS atualizado_em  timestamptz NOT NULL DEFAULT now(), '
    '  ADD COLUMN IF NOT EXISTS criado_por     int, '
    '  ADD COLUMN IF NOT EXISTS atualizado_por int',
    p_schema, p_tabela, t_atual
  );
  EXECUTE format('UPDATE %1$I.%2$I SET criado_por = %3$L, atualizado_por = %3$L WHERE criado_por IS NULL',
                  p_schema, p_tabela, p_usuario);
  BEGIN
    EXECUTE format('ALTER TABLE %1$I.%2$I ADD CONSTRAINT c_%3$s_globalid_u UNIQUE (globalid)',
                    p_schema, p_tabela, nome_curto);
  EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL; END;
  BEGIN
    EXECUTE format('ALTER SEQUENCE %1$I.%2$I_fid_seq MAXVALUE 2147483647 NO CYCLE', p_schema, p_tabela);
  EXCEPTION WHEN undefined_table THEN NULL; END;
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_geom_gix ON %1$I.%3$I USING gist (geom)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('CREATE INDEX IF NOT EXISTS c_%2$s_versao_ix ON %1$I.%3$I (atualizado_em)',
                  p_schema, nome_curto, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I ENABLE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('ALTER TABLE %1$I.%2$I FORCE ROW LEVEL SECURITY', p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_c_%2$s ON %1$I.%3$I', p_schema, nome_curto, p_tabela);
  EXECUTE format(
    'CREATE POLICY p_c_%2$s ON %1$I.%3$I FOR ALL TO plat_app, plat_leitor '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, p_tabela
  );
  EXECUTE format('DROP TRIGGER IF EXISTS tg_versao ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_versao BEFORE UPDATE ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_versao()', p_schema, p_tabela);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_tenant ON %1$I.%2$I', p_schema, p_tabela);
  EXECUTE format('CREATE TRIGGER tg_tenant BEFORE INSERT ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir()', p_schema, p_tabela);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, p_tabela, 'plat camada (L0-04)');
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, p_tabela);
END $$;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;

-- tenant_criar: mesma função da 029, com o prefixo de instalação no schema de dado
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int; esq text;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_slug IN ('plataforma','plat','public','admin','api','static','svc','ogc','tiles','saude','entrar','conta') THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  esq := plat.camada_schema_prefixo() || p_slug;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', esq);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', esq);
  RETURN QUERY SELECT tid, uid;
END $$;

-- migração do que já existe: renomeia d_<slug> desta instalação para <prefixo><slug> e conserta o nome
-- gravado em plat.item.dados->>'schema'. Só toca schema cujo dono é o papel DESTA instalação: o d_demo
-- que ficou com o papel de outra instalação continua onde está (e deixa de ser usado por esta).
DO $$
DECLARE r record; antigo text; novo text; dono text;
BEGIN
  FOR r IN SELECT slug FROM plat.tenant LOOP
    antigo := 'd_' || r.slug;
    novo := plat.camada_schema_prefixo() || r.slug;
    IF novo <> antigo AND NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = novo) THEN
      SELECT pg_get_userbyid(nspowner) INTO dono FROM pg_namespace WHERE nspname = antigo;
      IF dono = 'plat_app' THEN
        EXECUTE format('ALTER SCHEMA %I RENAME TO %I', antigo, novo);
      END IF;
    END IF;
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', novo);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', novo);
  END LOOP;
  UPDATE plat.item i
     SET dados = jsonb_set(i.dados, '{schema}', to_jsonb(plat.camada_schema_prefixo() || t.slug))
    FROM plat.tenant t
   WHERE t.id = i.tenant_id AND i.tipo = 'camada_vetorial'
     AND i.dados->>'schema' = 'd_' || t.slug
     AND plat.camada_schema_prefixo() <> 'd_';
END $$;
