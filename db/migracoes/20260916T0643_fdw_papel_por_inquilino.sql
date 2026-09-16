-- 20260916T0643_fdw_papel_por_inquilino: item L0-04-i-fonte-registrada, correção de segurança (adversário de
-- linha L0, turno 9, laudo `linha-L0-laudo-adversario-1.md`, achado 4 e seção `L0-04-i-fonte-registrada`;
-- teste `tests/api/adversario/test_l0_fonte_registrada_credencial.py`). NÃO edita
-- `20260907T0148_fonte_registrada_postgres_fdw.sql` (arquivo aplicado é imutável, ADR 0014) — substitui só o
-- CORPO de `plat.conexao_fdw_publicar` por `CREATE OR REPLACE FUNCTION` de mesma assinatura.
--
-- ACHADO: `CREATE USER MAPPING FOR session_user ... OPTIONS (password %L)` grava a senha do Postgres externo
-- em `pg_user_mapping.umoptions`, um catálogo PERSISTENTE (não uma variável de sessão, como a seção 2 do ADR
-- 20260907T0148 avaliava). `session_user` é o MESMO papel de login compartilhado por TODOS os inquilinos
-- desta instalação (ADR 0001: isolamento por RLS/GUC, nunca por papel de banco — `plat_app` em produção,
-- `plat_t<trilha>_app` em cada trilha). `pg_user_mappings.umoptions` só devolve NULL para quem NÃO É o dono
-- do mapeamento (nem tem papel herdado dele) nem superusuário; como o dono era sempre esse papel
-- compartilhado, qualquer sessão autenticada de QUALQUER inquilino lia, para sempre,
-- `SELECT umoptions FROM pg_user_mappings` e via a senha de conexão postgres_fdw de qualquer OUTRO inquilino.
--
-- CONSERTO: o USER MAPPING passa a pertencer a um papel Postgres NOLOGIN por INQUILINO
-- (`plat_fdw_<slug>`, nunca concedido a `plat_app`/`plat_t<trilha>_app` — ninguém faz SET ROLE para ele) em
-- vez de `session_user`. Como a VIEW final (`vf_<hash>`) deixa de ser `security_invoker` e passa a ter esse
-- papel como DONA, o Postgres resolve o privilégio sobre a FOREIGN TABLE (e o USER MAPPING usado para abrir a
-- conexão remota) pela identidade da DONA da view, não de quem consulta — o MESMO padrão já provado e medido
-- em `20260906T15521aa_acervo_publicacao.sql` ("REFUTAÇÃO REGISTRADA": security_invoker checa o privilégio
-- de quem chama contra a tabela de base; o modo padrão checa contra o DONO da view). `plat_app` continua
-- só com GRANT SELECT na VIEW (nunca na FOREIGN TABLE, nunca no SERVER/USER MAPPING) — o mesmo raio de
-- exposição de antes, só que agora `pg_has_role(plat_fdw_<slug>, 'USAGE')` é FALSO para o papel de login
-- compartilhado (nunca foi feito GRANT desse papel a ele), então `pg_user_mappings.umoptions` volta NULL para
-- qualquer sessão de aplicação, de qualquer inquilino.
--
-- Isto NÃO é isolamento de DADO por papel de banco (ADR 0001 continua valendo: quem decide quais linhas
-- aparecem é o filtro `WHERE plat.tenant_atual() = <tenant_id>` já embutido na view, avaliado com o GUC de
-- sessão de sempre) — `plat_fdw_<slug>` é só um CONTÊINER DE CREDENCIAL, NOLOGIN, que nenhuma sessão de
-- aplicação jamais assume; existe unicamente para que o catálogo `pg_user_mapping` tenha um dono que a sessão
-- de aplicação não é nem herda.
--
-- pendência registrada (fora do escopo desta correção pontual): conexões `postgres_fdw` publicadas ANTES
-- desta migração mantêm o USER MAPPING antigo `FOR session_user` até a próxima publicação/republicação
-- daquela conexão (que já passa a criar o mapeamento novo, por-inquilino, e não apaga sozinha o antigo -- só
-- quem apaga a conexão inteira limpa o SERVER, `plat.conexao_fdw_remover`/DELETE /api/conexoes/{id}, mesma
-- pendência já registrada na ADR original).
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

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
  p_colunas     jsonb,
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
  papel_fdw   text;  -- dono do USER MAPPING e da VIEW final: 1 papel NOLOGIN por inquilino, nunca por conexão
                       -- (reaproveitado entre várias conexões postgres_fdw do MESMO inquilino) e nunca
                       -- concedido a plat_app/plat_t<trilha>_app -- é isso que impede a senha de aparecer em
                       -- pg_user_mappings para quem consulta com o papel de aplicação (ver comentário do
                       -- arquivo desta migração).
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
  papel_fdw := 'plat_fdw_' || p_slug;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = papel_fdw) THEN
    EXECUTE format('CREATE ROLE %I NOLOGIN', papel_fdw);
  END IF;

  SELECT EXISTS(SELECT 1 FROM pg_foreign_server WHERE srvname = servidor) INTO ja_tem_srv;
  IF NOT ja_tem_srv THEN
    EXECUTE format(
      'CREATE SERVER %I FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host %L, port %L, dbname %L, fetch_size %L)',
      servidor, p_host, p_porta::text, p_banco, '1000'
    );
  ELSE
    EXECUTE format('ALTER SERVER %I OPTIONS (SET host %L, SET port %L, SET dbname %L)', servidor, p_host, p_porta::text, p_banco);
  END IF;

  -- USER MAPPING é do papel-contêiner por inquilino (papel_fdw), nunca de session_user (achado L0-04-i /
  -- turno 9): session_user é o mesmo papel de login para todos os inquilinos, e o Postgres só esconde
  -- pg_user_mappings.umoptions de quem não é dono do mapeamento (nem herda o papel dono) nem superusuário.
  SELECT EXISTS(
    SELECT 1 FROM pg_user_mappings um JOIN pg_foreign_server s ON s.oid = um.srvid
    WHERE s.srvname = servidor AND um.usename = papel_fdw
  ) INTO ja_tem_map;
  IF ja_tem_map THEN
    EXECUTE format('ALTER USER MAPPING FOR %I SERVER %I OPTIONS (SET user %L, SET password %L)', papel_fdw, servidor, p_usuario_ext, p_senha);
  ELSE
    EXECUTE format('CREATE USER MAPPING FOR %I SERVER %I OPTIONS (user %L, password %L)', papel_fdw, servidor, p_usuario_ext, p_senha);
  END IF;
  EXECUTE format('GRANT USAGE ON FOREIGN SERVER %I TO %I', servidor, papel_fdw);

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
  -- a FOREIGN TABLE só concede SELECT ao papel-contêiner (papel_fdw), que é quem a VIEW abaixo usa como
  -- dona -- plat_app/plat_t<trilha>_app NUNCA recebe privilégio direto nela (nem consegue: não é membro de
  -- papel_fdw, então nem SET ROLE alcança o mapeamento).
  EXECUTE format('GRANT SELECT ON %I.%I TO %I', esquema_d, ft_nome, papel_fdw);
  -- SEM security_invoker: a view roda com o privilégio da DONA (papel_fdw) sobre a tabela estrangeira e
  -- sobre o USER MAPPING usado para abrir a conexão remota -- mesmo padrão medido e registrado em
  -- 20260906T15521aa_acervo_publicacao.sql ("REFUTAÇÃO REGISTRADA"). security_barrier continua para que o
  -- planejador não empurre um qual arbitrário do consultante para dentro do FDW scan.
  EXECUTE format(
    'CREATE OR REPLACE VIEW %I.%I WITH (security_barrier) AS SELECT %L::int AS tenant_id, %s FROM %I.%I WHERE plat.tenant_atual() = %L::int',
    esquema_d, view_nome, t_atual, col_lst_sql, esquema_d, ft_nome, t_atual
  );
  EXECUTE format('ALTER VIEW %I.%I OWNER TO %I', esquema_d, view_nome, papel_fdw);
  EXECUTE format('REVOKE ALL ON %I.%I FROM PUBLIC', esquema_d, view_nome);
  EXECUTE format('GRANT SELECT ON %I.%I TO %I', esquema_d, view_nome, session_user);

  RETURN QUERY SELECT esquema_d, view_nome;
END $$;

REVOKE ALL ON FUNCTION plat.conexao_fdw_publicar(uuid, text, text, int, text, text, text, text, text, jsonb, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.conexao_fdw_publicar(uuid, text, text, int, text, text, text, text, text, jsonb, int) TO plat_app;
