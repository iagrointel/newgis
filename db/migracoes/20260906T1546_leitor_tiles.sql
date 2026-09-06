-- 20260906T1546_leitor_tiles: item L2-04-a-leitor-rls-martin. Papel de leitura externa (Martin e qualquer
-- outro leitor de tile), contexto de inquilino obtido do token de serviço dentro do banco, e uma função de
-- tile por camada que só devolve MVT depois de o contexto estar posto. Idempotente. Sem BEGIN/COMMIT.
--
-- Por que dentro do banco: a RLS das tabelas d_<slug>.c_* (029_ingestao_vetor) já filtra por
-- plat.tenant_atual(). Se o Martin conectar com um papel sem BYPASSRLS e a primeira coisa que a função de
-- tile fizer for validar o token e pôr a GUC plat.tenant_id, o isolamento entre inquilinos passa a valer
-- para o Martin sem uma linha de código novo do lado do Martin (ADR 0001 seção 3.3).
--
-- Nome do papel de leitura: `plat.papel_leitor()`. Em produção devolve `plat_leitor` (o papel NOLOGIN que a
-- 029 criou); numa base de trilha/homologação, onde `plat` vira `plat_t<trilha>`, a mesma expressão devolve
-- `plat_t<trilha>_leitor`, porque o reescritor de schema (app/schema_ambiente.py) troca a palavra `plat`
-- também dentro do literal. É esse o único jeito de a mesma migração valer nos dois lugares sem um papel
-- global compartilhado entre trilhas.

-- ---------------------------------------------------------------- papel de leitura
CREATE OR REPLACE FUNCTION plat.papel_leitor() RETURNS text LANGUAGE sql IMMUTABLE AS
  $$ SELECT 'plat' || '_leitor' $$;

DO $$
DECLARE papel text := plat.papel_leitor();
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = papel) THEN
    EXECUTE format('CREATE ROLE %I NOLOGIN', papel);
  END IF;
  -- nunca dona de tabela, nunca superusuária, nunca com BYPASSRLS: é a cláusula do item
  EXECUTE format('ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT', papel);
  EXECUTE format('GRANT USAGE ON SCHEMA plat TO %I', papel);
  -- schemas de camada já existentes deste ambiente (novos ganham em plat.camada_schema_garantir).
  -- Só concede o que falta: um GRANT repetido reescreve a linha de pg_namespace e, com outra sessão fazendo
  -- DDL no MESMO schema (d_<slug> é compartilhado nesta máquina), sai `tuple concurrently updated`.
  EXECUTE (SELECT coalesce(string_agg(format('GRANT USAGE ON SCHEMA %I TO %I;', 'd_' || slug, papel), ' '),
                           'SELECT 1')
           FROM plat.tenant
           WHERE to_regnamespace('d_' || slug) IS NOT NULL
             AND NOT has_schema_privilege(papel, 'd_' || slug, 'USAGE'));
END $$;

-- ---------------------------------------------------------------- escopo de token dentro do banco
-- espelho de app/auth/escopos.py:cobre() — `admin:inquilino` cobre tudo, a base sem uuid cobre `base:<uuid>`.
CREATE OR REPLACE FUNCTION plat.escopo_cobre(p_escopos text[], p_base text, p_uuid uuid DEFAULT NULL)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT 'admin:inquilino' = ANY(p_escopos)
      OR p_base = ANY(p_escopos)
      OR (p_uuid IS NOT NULL AND (p_base || ':' || p_uuid::text) = ANY(p_escopos))
$$;

-- espelho de app/auth/sessao.py:_origem_permitida() — compara ORIGEM (esquema + host + porta); `*.` casa só
-- subdomínio, nunca o ápice.
CREATE OR REPLACE FUNCTION plat.origem_permitida(p_origem text, p_padroes jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE o text[]; p text[]; padrao text; host text; phost text; porta int; pporta int;
BEGIN
  o := regexp_match(coalesce(p_origem, ''), '^([A-Za-z][A-Za-z0-9+.-]*)://([^/:?#]+)(?::([0-9]{1,5}))?');
  IF o IS NULL THEN RETURN false; END IF;
  host  := lower(o[2]);
  porta := coalesce(o[3]::int, CASE WHEN lower(o[1]) = 'https' THEN 443 ELSE 80 END);
  FOR padrao IN SELECT jsonb_array_elements_text(p_padroes) LOOP
    p := regexp_match(padrao, '^([A-Za-z][A-Za-z0-9+.-]*)://([^/:?#]+)(?::([0-9]{1,5}))?');
    CONTINUE WHEN p IS NULL OR lower(p[1]) <> lower(o[1]);
    pporta := coalesce(p[3]::int, CASE WHEN lower(p[1]) = 'https' THEN 443 ELSE 80 END);
    CONTINUE WHEN pporta <> porta;
    phost := lower(p[2]);
    IF left(phost, 2) = '*.' THEN
      IF host LIKE ('%' || substr(phost, 2)) AND host <> substr(phost, 3) THEN RETURN true; END IF;
    ELSIF host LIKE replace(replace(phost, '*', '%'), '?', '_') THEN
      RETURN true;
    END IF;
  END LOOP;
  RETURN false;
END $$;

CREATE OR REPLACE FUNCTION plat.ip_permitido(p_ip text, p_faixas jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE faixa text; endereco inet;
BEGIN
  BEGIN endereco := p_ip::inet; EXCEPTION WHEN others THEN RETURN false; END;
  FOR faixa IN SELECT jsonb_array_elements_text(p_faixas) LOOP
    BEGIN
      IF endereco <<= faixa::inet THEN RETURN true; END IF;
    EXCEPTION WHEN others THEN CONTINUE;
    END;
  END LOOP;
  RETURN false;
END $$;

-- ---------------------------------------------------------------- prova de contexto do papel de leitura
-- A GUC `plat.tenant_id` é um parâmetro de configuração comum: QUALQUER papel conectado pode escrever nela.
-- Para plat_app isso não é problema (a senha da aplicação já é autoridade total sobre a API), mas o papel de
-- leitura conecta de fora e é COMPARTILHADO por todos os inquilinos: se a política de RLS dele olhasse só
-- `plat.tenant_atual()`, quem tivesse a senha do leitor faria `SET plat.tenant_id = <outro inquilino>` e leria
-- a camada alheia — foi exatamente esse o ataque previsto na refutação do item.
-- Por isso a política do papel de leitura olha `plat.tenant_leitor()`: o inquilino só vale se vier acompanhado
-- de uma PROVA (sha256 de um segredo que só função SECURITY DEFINER lê, mais o inquilino e o processo). A
-- prova é emitida por plat.contexto_por_token, isto é, só para quem apresentou um token de serviço válido
-- daquele inquilino. Sem token não há prova; com o token de A não se fabrica a prova de B.
CREATE TABLE IF NOT EXISTS plat.segredo_leitor (
  unico  boolean PRIMARY KEY DEFAULT true CHECK (unico),
  valor  text NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON plat.segredo_leitor FROM PUBLIC;
INSERT INTO plat.segredo_leitor(unico, valor)
VALUES (true, encode(sha256(convert_to(gen_random_uuid()::text || gen_random_uuid()::text, 'UTF8')), 'hex'))
ON CONFLICT (unico) DO NOTHING;

CREATE OR REPLACE FUNCTION plat.prova_leitor(p_tenant int) RETURNS text
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT encode(sha256(convert_to(s.valor || ':' || p_tenant::text || ':' || pg_backend_pid()::text, 'UTF8')), 'hex')
  FROM plat.segredo_leitor s WHERE s.unico
$$;

-- Devolve o inquilino do contexto SÓ quando a prova bate. É esta função que a política de RLS do papel de
-- leitura usa; `plat.tenant_atual()` continua valendo para plat_app.
CREATE OR REPLACE FUNCTION plat.tenant_leitor() RETURNS int
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT t.id FROM plat.tenant t
  WHERE t.id = NULLIF(current_setting('plat.tenant_id', true), '')::int
    AND NULLIF(current_setting('plat.prova', true), '') = plat.prova_leitor(t.id)
$$;

-- ---------------------------------------------------------------- contexto de inquilino a partir do token
-- Valida o token de serviço (reusa plat.auth_token da 002, que também carimba ultimo_uso/ultimo_ip), confere
-- escopo e restrição de Referer/IP, grava UMA linha em plat.log_acesso e põe a GUC plat.tenant_id na
-- TRANSAÇÃO (set_config(..., true)) — nunca na sessão, para que uma conexão de pool não vaze contexto entre
-- pedidos. Devolve o tenant_id. Toda recusa é uma exceção NOMEADA (a mensagem é o nome, sem dado do token).
CREATE OR REPLACE FUNCTION plat.contexto_por_token(
    p_token text,
    p_ip text DEFAULT NULL,
    p_origem text DEFAULT NULL,
    p_item uuid DEFAULT NULL,
    p_escopo text DEFAULT 'camada:ler',
    p_rota text DEFAULT '/tiles')
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  v_tenant int; v_usuario int; v_token int; v_login text; v_escopos text[]; v_restricao jsonb;
  v_revogado timestamptz; v_expira timestamptz; v_pendencia boolean;
  ini timestamptz := clock_timestamp(); ms int; motivo text;
BEGIN
  IF p_token IS NULL OR p_token = '' THEN
    motivo := 'token_ausente';
  ELSIF left(p_token, 5) <> 'plat_' OR length(p_token) <> 48 THEN
    motivo := 'token_invalido';
  ELSE
    -- plat.auth_token (003) devolve a linha mesmo revogada ou expirada, de propósito: quem decide o motivo
    -- legível do 401 é o chamador (app/auth/sessao.py faz assim). Aqui a decisão é a mesma, no banco.
    SELECT a.tenant_id, a.usuario_id, a.token_id, a.login, a.escopos, a.restricao,
           a.revogado_em, a.expira_em, a.trocar_senha
      INTO v_tenant, v_usuario, v_token, v_login, v_escopos, v_restricao, v_revogado, v_expira, v_pendencia
      FROM plat.auth_token(encode(sha256(convert_to(p_token, 'UTF8')), 'hex'), p_ip) a;
    IF v_tenant IS NULL THEN
      motivo := 'token_invalido';                                   -- inexistente, dono ou inquilino inativo
    ELSIF v_revogado IS NOT NULL THEN
      motivo := 'token_revogado';
    ELSIF v_expira IS NOT NULL AND v_expira <= now() THEN
      motivo := 'token_expirado';
    ELSIF v_pendencia THEN
      motivo := 'dono_com_pendencia';                               -- troca de senha pendente: token não vale
    ELSIF NOT plat.escopo_cobre(v_escopos, p_escopo, p_item) THEN
      motivo := 'escopo_insuficiente';
    ELSIF jsonb_array_length(coalesce(v_restricao -> 'ip', '[]'::jsonb)) > 0
          AND NOT plat.ip_permitido(p_ip, v_restricao -> 'ip') THEN
      motivo := 'ip_nao_permitido';                                 -- sem IP no pedido a recusa é a mesma
    ELSIF jsonb_array_length(coalesce(v_restricao -> 'referer', '[]'::jsonb)) > 0 THEN
      IF p_origem IS NULL OR p_origem = '' THEN
        motivo := 'referer_ausente';
      ELSIF NOT plat.origem_permitida(p_origem, v_restricao -> 'referer') THEN
        motivo := 'referer_nao_permitido';
      END IF;
    END IF;
  END IF;

  ms := (extract(epoch FROM clock_timestamp() - ini) * 1000)::int;
  IF motivo IS NOT NULL THEN
    PERFORM plat.log_registrar(v_tenant, v_usuario, v_token, p_ip, 'GET', p_rota,
                               CASE WHEN motivo = 'escopo_insuficiente' THEN 403 ELSE 401 END,
                               0, ms, 'contexto_por_token', motivo);
    RAISE EXCEPTION '%', motivo USING ERRCODE = '28000';
  END IF;

  PERFORM set_config('plat.tenant_id', v_tenant::text, true);
  PERFORM set_config('plat.usuario_id', v_usuario::text, true);
  PERFORM set_config('plat.login', v_login, true);
  PERFORM set_config('plat.prova', plat.prova_leitor(v_tenant), true);   -- prova do inquilino para a RLS do leitor
  PERFORM plat.log_registrar(v_tenant, v_usuario, v_token, p_ip, 'GET', p_rota, 200, 0, ms,
                             'contexto_por_token', 'ok');
  RETURN v_tenant;
END $$;

-- ---------------------------------------------------------------- função de tile por camada
-- Cria d_<slug>.t_<16 hex> para a tabela d_<slug>.c_<16 hex>. A função de tile é SECURITY INVOKER de
-- propósito: é a RLS do CHAMADOR (o papel de leitura) que filtra as linhas. O inquilino da camada é gravado
-- no corpo na criação: se o contexto posto pelo token for de outro inquilino, a função levanta
-- `tile_de_outro_inquilino` em vez de devolver um tile vazio (falha barulhenta, pedido do adversário).
CREATE OR REPLACE FUNCTION plat.camada_tile_garantir(p_schema text, p_tabela text, p_item uuid DEFAULT NULL)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  papel text := plat.papel_leitor();
  curto text; nome text; tid int; srid int; colunas text; corpo text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF to_regclass(format('%I.%I', p_schema, p_tabela)) IS NULL THEN
    RAISE EXCEPTION 'camada_inexistente';
  END IF;
  SELECT id INTO tid FROM plat.tenant WHERE 'd_' || slug = p_schema;
  IF tid IS NULL THEN RAISE EXCEPTION 'schema_sem_inquilino'; END IF;
  curto := substr(p_tabela, 3);
  nome  := 't_' || curto;
  SELECT coalesce(nullif(postgis_typmod_srid(a.atttypmod), 0), 4326) INTO srid
  FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%I.%I', p_schema, p_tabela))
    AND a.attname = 'geom' AND NOT a.attisdropped;
  IF srid IS NULL THEN RAISE EXCEPTION 'camada_sem_geometria'; END IF;

  -- atributos: tudo menos a geometria e as colunas de controle interno
  SELECT string_agg(format('t.%I', a.attname), ', ' ORDER BY a.attnum) INTO colunas
  FROM pg_attribute a WHERE a.attrelid = to_regclass(format('%I.%I', p_schema, p_tabela))
    AND a.attnum > 0 AND NOT a.attisdropped
    AND a.attname NOT IN ('geom', 'tenant_id', 'criado_por', 'atualizado_por');

  corpo := format($f$
CREATE OR REPLACE FUNCTION %1$I.%2$I(z integer, x integer, y integer, query_params json DEFAULT '{}'::json)
RETURNS bytea LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $corpo$
DECLARE ctx int; env geometry; mvt bytea;
BEGIN
  IF z < 0 OR z > 24 OR x < 0 OR y < 0 OR x >= (1 << z) OR y >= (1 << z) THEN
    RAISE EXCEPTION 'zxy_invalido' USING ERRCODE = '22023';
  END IF;
  ctx := plat.contexto_por_token(query_params->>'token', query_params->>'ip', query_params->>'origem',
                                 %6$L::uuid, 'camada:ler', %7$L);
  IF ctx IS DISTINCT FROM %3$L::int THEN
    RAISE EXCEPTION 'tile_de_outro_inquilino' USING ERRCODE = '42501';
  END IF;
  env := ST_TileEnvelope(z, x, y);
  SELECT ST_AsMVT(q, %2$L, 4096, 'geom') INTO mvt FROM (
    SELECT ST_AsMVTGeom(ST_Transform(t.geom, 3857), env, 4096, 64, true) AS geom%5$s
    FROM %1$I.%4$I t
    WHERE t.geom && ST_Transform(env, %8$L::int)
  ) q;
  RETURN coalesce(mvt, ''::bytea);
END $corpo$
$f$,
    p_schema, nome, tid, p_tabela,
    CASE WHEN colunas IS NULL OR colunas = '' THEN '' ELSE ', ' || colunas END,
    p_item, '/tiles/' || p_schema || '/' || nome, srid);
  EXECUTE corpo;

  -- Política de RLS do papel de leitura: separada da de plat_app e ancorada na PROVA, não na GUC crua.
  -- A política ampla da 029 (`FOR ALL TO plat_app, plat_leitor`) é reescrita aqui SEM o papel de leitura —
  -- com ele dentro, um `SET plat.tenant_id` bastaria para ler a camada de outro inquilino.
  EXECUTE format('DROP POLICY IF EXISTS p_c_%s ON %I.%I', curto, p_schema, p_tabela);
  EXECUTE format('CREATE POLICY p_c_%s ON %I.%I FOR ALL TO plat_app '
                 'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
                 curto, p_schema, p_tabela);
  EXECUTE format('DROP POLICY IF EXISTS p_c_%s_leitor ON %I.%I', curto, p_schema, p_tabela);
  EXECUTE format('CREATE POLICY p_c_%s_leitor ON %I.%I FOR SELECT TO %I '
                 'USING (tenant_id = (SELECT plat.tenant_leitor()))',
                 curto, p_schema, p_tabela, papel);

  EXECUTE format('COMMENT ON FUNCTION %I.%I(integer,integer,integer,json) IS %L', p_schema, nome,
                 'tile MVT da camada ' || p_tabela || ' (item L2-04-a); contexto por token');
  EXECUTE format('REVOKE ALL ON FUNCTION %I.%I(integer,integer,integer,json) FROM PUBLIC', p_schema, nome);
  IF NOT has_schema_privilege(papel, p_schema, 'USAGE') THEN            -- ver nota do GRANT acima
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', p_schema, papel);
  END IF;
  IF NOT has_table_privilege(papel, format('%I.%I', p_schema, p_tabela), 'SELECT') THEN
    EXECUTE format('GRANT SELECT ON %I.%I TO %I', p_schema, p_tabela, papel);
  END IF;
  EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(integer,integer,integer,json) TO %I, plat_app',
                 p_schema, nome, papel);
  RETURN nome;
END $$;

-- A função de tile não é dona de plat_app (quem a cria é SECURITY DEFINER, isto é, postgres), então quem
-- apaga a camada precisa de uma porta para apagá-la junto — senão fica função apontando para tabela que já
-- não existe. app/catalogo/destruidores.py chama esta antes do DROP TABLE.
CREATE OR REPLACE FUNCTION plat.camada_tile_apagar(p_schema text, p_tabela text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nome text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  nome := 't_' || substr(p_tabela, 3);
  IF to_regprocedure(format('%I.%I(integer,integer,integer,json)', p_schema, nome)) IS NULL THEN
    RETURN false;
  END IF;
  EXECUTE format('DROP FUNCTION %I.%I(integer,integer,integer,json)', p_schema, nome);
  RETURN true;
END $$;

-- ---------------------------------------------------------------- privilégio de leitura do papel
-- O papel de leitura precisa de EXECUTE nas funções que a de tile chama. O SELECT nas tabelas de camada é
-- concedido uma a uma (plat.camada_preparar da 029 e plat.camada_tile_garantir abaixo), nunca em varredura
-- por pg_class: o schema d_<slug> é compartilhado com os outros ambientes desta máquina.
DO $$
DECLARE papel text := plat.papel_leitor();
BEGIN
  EXECUTE format('GRANT EXECUTE ON FUNCTION plat.contexto_por_token(text,text,text,uuid,text,text) TO %I', papel);
  EXECUTE format('GRANT EXECUTE ON FUNCTION plat.tenant_atual(), plat.usuario_atual(), '
                 'plat.escopo_cobre(text[],text,uuid), plat.origem_permitida(text,jsonb), '
                 'plat.ip_permitido(text,jsonb), plat.papel_leitor(), plat.tenant_leitor() TO %I', papel);
END $$;
REVOKE EXECUTE ON FUNCTION plat.contexto_por_token(text,text,text,uuid,text,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.prova_leitor(int) FROM PUBLIC;   -- só quem já provou o token recebe a prova
REVOKE EXECUTE ON FUNCTION plat.tenant_leitor() FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION plat.tenant_leitor() TO plat_app;
REVOKE EXECUTE ON FUNCTION plat.camada_tile_garantir(text,text,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION plat.camada_tile_garantir(text,text,uuid) TO plat_app;
REVOKE EXECUTE ON FUNCTION plat.camada_tile_apagar(text,text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION plat.camada_tile_apagar(text,text) TO plat_app;
GRANT  EXECUTE ON FUNCTION plat.contexto_por_token(text,text,text,uuid,text,text) TO plat_app;

-- ---------------------------------------------------------------- retroativo: função de tile das camadas já
-- publicadas NESTE ambiente. A varredura é pelo CATÁLOGO (plat.item), nunca pelo pg_class: o schema d_<slug>
-- é compartilhado entre ambientes (produção, homologação e as bases por trilha convivem em d_demo), e só o
-- catálogo diz quais camadas são deste ambiente.
DO $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN SELECT i.id, i.dados->>'schema' AS esquema, i.dados->>'tabela' AS tabela
           FROM plat.item i
           WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
             AND coalesce(i.dados->>'fonte', 'hospedada') = 'hospedada'
             AND i.dados->>'schema' ~ '^d_[a-z0-9_]{1,60}$' AND i.dados->>'tabela' ~ '^c_[0-9a-f]{16}$' LOOP
    CONTINUE WHEN to_regclass(format('%I.%I', r.esquema, r.tabela)) IS NULL;
    PERFORM plat.camada_tile_garantir(r.esquema, r.tabela, r.id);
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'funções de tile garantidas para % camada(s) do catálogo', n;
END $$;
