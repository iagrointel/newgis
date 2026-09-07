-- Trinco de aconselhamento por transação nas funções SECURITY DEFINER que fazem DDL (ADR 0025).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- O DEFEITO (medido em 07/09/2026 em produção-de-teste, sob carga): duas sessões do MESMO inquilino
-- publicando camada ao mesmo tempo caem em `plat.camada_schema_garantir(slug)`, que faz
--
--     CREATE SCHEMA IF NOT EXISTS d_<slug> AUTHORIZATION plat_app;
--     GRANT USAGE ON SCHEMA d_<slug> TO plat_leitor;
--
-- sem nenhuma serialização. Medição isolada com 6 sessões simultâneas no mesmo schema: 3 das 6
-- terminaram com `ERROR: tuple concurrently updated`. O job de ingestão morre no passo 0 e a
-- importação inteira falha; para o cliente, publicar duas camadas ao mesmo tempo é o caminho normal.
--
-- POR QUE `IF NOT EXISTS` NÃO BASTA (as duas metades falham por motivos diferentes):
--  1. `CREATE SCHEMA IF NOT EXISTS` não é atômico contra OUTRA transação criando o mesmo schema.
--     O teste de existência lê o catálogo com a visão da própria transação; a linha da concorrente
--     ainda não está confirmada. As duas passam pelo teste e a segunda a confirmar leva
--     `duplicate_schema` (ou unique_violation no índice de pg_namespace).
--  2. O `GRANT` não tem `IF NOT EXISTS` nenhum: ele ATUALIZA a coluna `nspacl` da MESMA linha de
--     `pg_namespace`. Duas atualizações concorrentes da mesma linha de catálogo não passam pelo
--     EvalPlanQual que salva uma tabela comum — o executor de catálogo aborta com
--     `tuple concurrently updated` (XX000). Isto acontece MESMO quando o schema já existe, isto é,
--     no caso mais comum de todos: o inquilino antigo publicando a décima camada.
--     Repetir a transação (retry) esconderia o defeito, custaria latência e ainda deixaria o
--     `duplicate_schema` do item 1 vivo.
--
-- A SAÍDA: `pg_advisory_xact_lock(hashtext(<chave>))` tomado ANTES do DDL, com chave derivada do
-- objeto que o DDL toca (o slug, o nome da tabela, o nome da partição). O trinco é de aconselhamento
-- (não bloqueia mais nada no banco), é de TRANSAÇÃO (some sozinho no COMMIT/ROLLBACK, sem risco de
-- ficar preso se a sessão morrer) e é POR CHAVE: inquilinos diferentes não esperam um pelo outro,
-- provado em `tests/api/test_camada_schema_corrida.py::test_inquilinos_diferentes_nao_esperam`.
-- Colisão de `hashtext` entre chaves distintas só causaria espera desnecessária, nunca erro.
-- O espaço de trinco é POR BANCO, que é exatamente o escopo certo: os schemas `d_<slug>` também são
-- globais ao banco (não têm prefixo de instalação), logo produção, homologação e trilhas disputam o
-- mesmo objeto e têm de disputar o mesmo trinco.
--
-- A CLASSE, não o caso: todas as funções SECURITY DEFINER que emitem DDL em tempo de execução, e não
-- só a que foi flagrada. Além de `camada_schema_garantir`: `camada_preparar` (DDL na tabela da camada
-- + GRANT), `tenant_criar` (cria o MESMO d_<slug>, logo divide a chave), `evento_particao_garantir` e
-- `log_particao_garantir` (CREATE TABLE PARTITION OF + REVOKE + ALTER + CREATE POLICY na primeira
-- escrita de cada mês — a mesma corrida, com a virada do mês como gatilho), e os dois expurgadores,
-- que largam partição e por isso disputam a mesma chave da partição.
--
-- ATENÇÃO A QUEM JUNTAR RAMOS: este arquivo REDEFINE funções inteiras. Se outro ramo redefinir
-- qualquer uma delas depois deste carimbo de tempo, o trinco se perde em silêncio. Existe guarda:
-- `tests/api/test_camada_schema_corrida.py::test_toda_funcao_com_ddl_tem_trinco` lê o corpo vivo das
-- funções em `pg_get_functiondef` e reprova qualquer uma que faça DDL sem `pg_advisory_xact_lock`.
-- O alfabeto de slug abaixo é o de `db/migracoes/20260906T1607_slug_ingestao_reconciliado.sql`
-- (ramo wt/g3fix, ainda não juntado): mantido de propósito para que a junção, em qualquer ordem,
-- não perca nem o alfabeto nem o trinco.

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  -- mesmo alfabeto do CHECK de plat.tenant.slug (migração 002), mais '_' por compatibilidade
  IF p_slug !~ '^[a-z0-9][a-z0-9_-]{1,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || p_slug));
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
END $$;

CREATE OR REPLACE FUNCTION plat.camada_preparar(p_schema text, p_tabela text, p_srid int, p_tipo text, p_usuario int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9][a-z0-9_-]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  nome_curto := substr(p_tabela, 3);  -- os 16 hex, sem o prefixo c_ (nome de índice/política/trigger não colide)
  -- trinco pela TABELA: duas tentativas do mesmo carregamento (reexecução do job, retomada) fazem
  -- ALTER/CREATE INDEX/CREATE POLICY na mesma tabela e atualizam as mesmas linhas de pg_class/pg_attribute.
  PERFORM pg_advisory_xact_lock(hashtext('camada_preparar:' || p_schema || '.' || p_tabela));

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

-- tenant_criar cria o MESMO d_<slug> que camada_schema_garantir: divide a chave, senão criar inquilino
-- ao mesmo tempo que outra sessão publica camada nele volta a colidir.
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_slug IN ('plataforma','plat','public','admin','api','static','svc','ogc','tiles','saude','entrar','conta') THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config) VALUES (p_slug, p_nome, coalesce(p_config, '{}'::jsonb)) RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || p_slug));
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
  RETURN QUERY SELECT tid, uid;
END $$;

-- Partições mensais: a corrida acontece na PRIMEIRA escrita de cada mês, quando duas requisições
-- registram evento (ou acesso) ao mesmo tempo e as duas veem a partição faltando.
CREATE OR REPLACE FUNCTION plat.evento_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
  fim := (ini + interval '1 month')::date;
  nome := format('evento_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('particao:plat.' || nome));
    -- reconferido DEPOIS do trinco: quem esperou já encontra a partição criada pela outra sessão
    IF to_regclass('plat.' || nome) IS NULL THEN
      EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.evento FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
      EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
      EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
      EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
    END IF;
  END IF;
  RETURN nome;
END $$;

CREATE OR REPLACE FUNCTION plat.log_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
  fim := (ini + interval '1 month')::date;
  nome := format('log_acesso_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('particao:plat.' || nome));
    IF to_regclass('plat.' || nome) IS NULL THEN
      EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.log_acesso FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
      EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
      EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
      EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
    END IF;
  END IF;
  RETURN nome;
END $$;

-- Os expurgadores largam partição: mesma chave da partição, para não correrem contra o garantir nem
-- contra outra rodada de manutenção.
CREATE OR REPLACE FUNCTION plat.evento_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
BEGIN
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.evento'::regclass LOOP
    IF to_date(substring(r.relname FROM 'y(\d{4})m(\d{2})$'), 'YYYY') IS NOT NULL
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      PERFORM pg_advisory_xact_lock(hashtext('particao:plat.' || r.relname));
      IF to_regclass('plat.' || r.relname) IS NOT NULL THEN
        EXECUTE format('DROP TABLE plat.%I', r.relname);
        n := n + 1;
      END IF;
    END IF;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.log_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
BEGIN
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.log_acesso'::regclass LOOP
    IF (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      PERFORM pg_advisory_xact_lock(hashtext('particao:plat.' || r.relname));
      IF to_regclass('plat.' || r.relname) IS NOT NULL THEN
        EXECUTE format('DROP TABLE plat.%I', r.relname);
        n := n + 1;
      END IF;
    END IF;
  END LOOP;
  RETURN n;
END $$;

-- Privilégio: repete o que a 033 declarou para as duas funções de ingestão (CREATE OR REPLACE preserva a
-- ACL, mas repetir é idempotente e deixa a migração autossuficiente). As demais funções redefinidas aqui
-- NÃO tinham privilégio declarado em migração nenhuma: mexer nelas mudaria o acesso do worker, e a
-- correção de concorrência não é lugar para isso.
REVOKE EXECUTE ON FUNCTION plat.camada_schema_garantir(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_schema_garantir(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.camada_preparar(text, text, int, text, int) TO plat_app;
