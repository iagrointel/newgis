-- 20260907T0148_fonte_registrada_postgres_fdw: item L0-04-i-fonte-registrada (docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md). "Fonte de dado
-- registrada" = o "data store item" da Esri 11.4 / o "store" do GeoServer, mas só para o conector
-- postgres_fdw (os demais tipos de `plat.conexao` já existem no vocabulário desde a 030; pasta de rede e
-- bucket S3 externo ficam para L6-02). O MODELO de conexão (`plat.conexao`, credencial cifrada, SSRF) já
-- existe (L6-02-a, migração 030/036) — esta migração só acrescenta o que falta para o tipo `postgres_fdw`:
-- extensão instalada, e uma função SECURITY DEFINER que cria SERVER + USER MAPPING + FOREIGN TABLE + VIEW,
-- porque `plat_app` não tem CREATE no banco (ADR 0001) nem USAGE na extensão postgres_fdw — só a função
-- (dona: postgres) tem os dois.
--
-- Desenho da view: uma tabela estrangeira não aceita política de RLS do jeito de `plat.camada_preparar`
-- (a política olharia uma coluna `tenant_id` que a tabela remota nunca tem); em vez disso, a VIEW que
-- embrulha a tabela estrangeira INJETA um `tenant_id` (constante, o do inquilino que publicou) e filtra
-- `WHERE plat.tenant_atual() = <esse tenant_id>` — o mesmo predicado que uma política de RLS teria, só que
-- expresso em SQL de view porque o objeto de baixo é estrangeiro. GRANT SELECT só para `plat_app` (nunca
-- PUBLIC), então mesmo com esse predicado a view não é visível de fora da role da aplicação.
--
-- 1 CREATE SERVER por CONEXÃO (reaproveitado entre tabelas publicadas da mesma conexão); ALTER SERVER/ALTER
-- USER MAPPING em vez de recriar quando já existem (credencial pode ter mudado desde a última publicação).
-- Nome do servidor = `fdw_<uuid sem hifens>` (determinístico, 1:1 com o id de `plat.conexao`); nome da
-- tabela/view = hash sha256 curto de `conexao_id:schema.tabela` (16 hex; nunca o nome bruto da tabela do
-- cliente, que já foi validado por regex no Python mas passa por segunda validação aqui, defesa em
-- profundidade — SECURITY DEFINER roda como postgres, então CADA identificador que chega em `format(%I)`
-- teria de ser são mesmo que a camada Python fosse contornada).
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE OR REPLACE FUNCTION plat.conexao_fdw_publicar(
  p_conexao_id  uuid,
  p_slug        text,
  p_host        text,
  p_porta       int,
  p_banco       text,
  p_usuario_ext text,
  p_senha       text,
  p_schema_ext  text,
  p_tabela_ext  text,
  p_colunas     jsonb,   -- [{"nome":"...", "tipo_pg":"text"}, ...] — já validado em Python contra o que o
                          -- information_schema do banco remoto declarou, nunca o que o chamador alegou
  p_tenant_id   int
) RETURNS TABLE(schema_local text, tabela_local text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  t_atual     int;
  servidor    text;
  ft_nome     text;
  view_nome   text;
  hash_curto  text;
  esquema_d   text;
  col_def_sql text;
  col_lst_sql text;
  ja_tem_srv  boolean;
  ja_tem_map  boolean;
BEGIN
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL OR t_atual IS DISTINCT FROM p_tenant_id THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND slug = p_slug) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.conexao WHERE id = p_conexao_id AND tenant_id = t_atual AND tipo = 'postgres_fdw') THEN
    RAISE EXCEPTION 'conexao_invalida_ou_de_outro_inquilino';
  END IF;
  -- defesa em profundidade: os mesmos regex que app/conexao/pgfdw.py já checou em Python, checados de novo
  -- aqui (função dona postgres; nunca confiar só na camada de cima para EXECUTE format com %I)
  IF p_schema_ext !~ '^[A-Za-z_][A-Za-z0-9_]{0,62}$' OR p_tabela_ext !~ '^[A-Za-z_][A-Za-z0-9_]{0,62}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF p_slug !~ '^[a-z][a-z0-9_]{0,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF jsonb_typeof(p_colunas) IS DISTINCT FROM 'array' OR jsonb_array_length(p_colunas) = 0 THEN
    RAISE EXCEPTION 'sem_colunas';
  END IF;

  esquema_d := 'd_' || p_slug;
  servidor  := 'fdw_' || replace(p_conexao_id::text, '-', '');
  hash_curto := substr(encode(digest(p_conexao_id::text || ':' || p_schema_ext || '.' || p_tabela_ext, 'sha256'), 'hex'), 1, 16);
  ft_nome   := 'ft_' || hash_curto;
  view_nome := 'vf_' || hash_curto;

  SELECT EXISTS(SELECT 1 FROM pg_foreign_server WHERE srvname = servidor) INTO ja_tem_srv;
  IF NOT ja_tem_srv THEN
    EXECUTE format(
      'CREATE SERVER %I FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host %L, port %L, dbname %L, fetch_size %L)',
      servidor, p_host, p_porta::text, p_banco, '1000'
    );
  ELSE
    EXECUTE format('ALTER SERVER %I OPTIONS (SET host %L, SET port %L, SET dbname %L)', servidor, p_host, p_porta::text, p_banco);
  END IF;

  SELECT EXISTS(
    SELECT 1 FROM pg_user_mappings um JOIN pg_foreign_server s ON s.oid = um.srvid
    WHERE s.srvname = servidor AND um.usename = session_user
  ) INTO ja_tem_map;
  IF ja_tem_map THEN
    EXECUTE format('ALTER USER MAPPING FOR %I SERVER %I OPTIONS (SET user %L, SET password %L)', session_user, servidor, p_usuario_ext, p_senha);
  ELSE
    EXECUTE format('CREATE USER MAPPING FOR %I SERVER %I OPTIONS (user %L, password %L)', session_user, servidor, p_usuario_ext, p_senha);
  END IF;
  EXECUTE format('GRANT USAGE ON FOREIGN SERVER %I TO %I', servidor, session_user);

  SELECT string_agg(format('%I %s', c->>'nome', c->>'tipo_pg'), ', ' ORDER BY ord)
    INTO col_def_sql
    FROM jsonb_array_elements(p_colunas) WITH ORDINALITY AS t(c, ord);
  SELECT string_agg(format('%I', c->>'nome'), ', ' ORDER BY ord)
    INTO col_lst_sql
    FROM jsonb_array_elements(p_colunas) WITH ORDINALITY AS t(c, ord);

  EXECUTE format('DROP FOREIGN TABLE IF EXISTS %I.%I CASCADE', esquema_d, ft_nome);
  EXECUTE format(
    'CREATE FOREIGN TABLE %I.%I (%s) SERVER %I OPTIONS (schema_name %L, table_name %L)',
    esquema_d, ft_nome, col_def_sql, servidor, p_schema_ext, p_tabela_ext
  );
  EXECUTE format('GRANT SELECT ON %I.%I TO %I', esquema_d, ft_nome, session_user);  -- security_invoker na view abaixo exige que QUEM CONSULTA (session_user), não o dono da view, tenha SELECT direto na tabela estrangeira
  EXECUTE format(
    'CREATE OR REPLACE VIEW %I.%I WITH (security_barrier, security_invoker) AS SELECT %L::int AS tenant_id, %s FROM %I.%I WHERE plat.tenant_atual() = %L::int',
    esquema_d, view_nome, t_atual, col_lst_sql, esquema_d, ft_nome, t_atual
  );
  EXECUTE format('REVOKE ALL ON %I.%I FROM PUBLIC', esquema_d, view_nome);
  EXECUTE format('GRANT SELECT ON %I.%I TO %I', esquema_d, view_nome, session_user);

  RETURN QUERY SELECT esquema_d, view_nome;
END $$;

REVOKE ALL ON FUNCTION plat.conexao_fdw_publicar(uuid, text, text, int, text, text, text, text, text, jsonb, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.conexao_fdw_publicar(uuid, text, text, int, text, text, text, text, text, jsonb, int) TO plat_app;

-- ---------------------------------------------------------------- desfazer view/tabela-estrangeira quando a
-- conexão cai fora de circulação (nunca apaga o item de catálogo, ADR 0011 seção "camada continua no
-- catálogo com estado de fonte indisponível" — só o objeto físico intermediário some se o dono apagar)
CREATE OR REPLACE FUNCTION plat.conexao_fdw_remover(p_slug text, p_tabela_local text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; esquema_d text; ft_nome text;
BEGIN
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN RAISE EXCEPTION 'sem_tenant_no_contexto'; END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND slug = p_slug) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  IF p_tabela_local !~ '^vf_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  esquema_d := 'd_' || p_slug;
  ft_nome := 'ft_' || substr(p_tabela_local, 4);
  EXECUTE format('DROP VIEW IF EXISTS %I.%I', esquema_d, p_tabela_local);
  EXECUTE format('DROP FOREIGN TABLE IF EXISTS %I.%I CASCADE', esquema_d, ft_nome);
END $$;
REVOKE ALL ON FUNCTION plat.conexao_fdw_remover(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.conexao_fdw_remover(text, text) TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/publicar_em_massa', 'lote de tabelas de uma conexão postgres_fdw publicado como camadas referenciadas'),
  ('conexoes/fonte_indisponivel', 'camada referenciada marcada como fonte indisponível (a conexão de origem falhou)')
ON CONFLICT (nome) DO NOTHING;
