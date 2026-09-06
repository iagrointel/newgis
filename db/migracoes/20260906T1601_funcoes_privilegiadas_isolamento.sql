-- 20260906T1601_funcoes_privilegiadas_isolamento
--
-- Fecha a CLASSE de defeito medida em 06/09/2026 por dois adversários independentes em grupos diferentes
-- (laco/handoffs/T3/ataque-g2-ADVERSARIO.md achado G2-1/G2-2 e ataque-g4-ADVERSARIO.md achado G4-10):
-- função SECURITY DEFINER do schema `plat` que recebe o identificador do alvo por argumento, roda como o dono
-- (postgres, fora da RLS) e NÃO compara o alvo com o inquilino do contexto, nem confere o argumento.
--
-- A varredura das 102 funções SECURITY DEFINER está em laco/handoffs/T3/VARREDURA-funcoes-privilegiadas.md.
-- Esta migração aplica três remédios, sempre o mesmo, para que o padrão seja copiável:
--   1. `plat.inquilino_do_argumento(int)` / `plat.inquilino_do_slug(text)`: recusa argumento de OUTRO inquilino
--      quando há inquilino no contexto; aceita quando não há contexto (rota anônima, worker) ou quando o
--      contexto é o inquilino técnico `plataforma` — exatamente a regra que `plat.item_expurgar` e
--      `plat.lixeira_expurgar` já usavam à mão desde a 011.
--   2. `plat.so_manutencao(text)`: função de expurgo global só roda sem contexto ou sob `plataforma`. Fecha o
--      caminho medido "admin de um inquilino enfileira o periódico e o expurgo varre todos os inquilinos".
--   3. validação de argumento: número de meses/dias/segundos/itens a manter tem piso; nulo e negativo levantam.
--
-- Também reafirma permissões: as três funções com EXECUTE para PUBLIC (`tg_conexao_atualizado_em` da 030,
-- `upload_reservado_bytes` e `uploads_expirar_candidatos` da 046) perdem o PUBLIC — é o que deixa
-- tests/api/test_funcoes_seguras.py e tests/api/catalogo/test_eventos_e_seguranca.py VERMELHOS no master
-- desde 9df2cff (06/09 13:13 UTC, migração 030) — e `plat.tenant_apagar_interno` volta a não ter plat_app
-- (a 009 já revogava; em produção o EXECUTE reapareceu, medido em 06/09).
--
-- Idempotente (CREATE OR REPLACE + REVOKE/GRANT). Sem BEGIN/COMMIT.

-- ---------------------------------------------------------------- 1. guardas reusáveis

CREATE OR REPLACE FUNCTION plat.inquilino_do_argumento(p_tenant int) RETURNS int
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ctx int := plat.tenant_atual();
BEGIN
  IF p_tenant IS NULL THEN
    RAISE EXCEPTION 'inquilino_argumento_nulo' USING HINT = 'a função exige o id do inquilino';
  END IF;
  IF ctx IS NULL OR ctx = p_tenant THEN RETURN p_tenant; END IF;
  IF EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = ctx AND t.slug = 'plataforma') THEN RETURN p_tenant; END IF;
  RAISE EXCEPTION 'contexto_de_outro_inquilino'
    USING HINT = 'a função exige o contexto do inquilino do argumento';
END $$;
COMMENT ON FUNCTION plat.inquilino_do_argumento(int) IS
  'Guarda de isolamento para função SECURITY DEFINER que recebe tenant_id por argumento: aceita sem contexto '
  '(rota anônima/worker) ou sob o inquilino técnico plataforma; recusa alvo de outro inquilino.';

CREATE OR REPLACE FUNCTION plat.inquilino_do_slug(p_slug text) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ctx int := plat.tenant_atual(); alvo int;
BEGIN
  IF ctx IS NULL THEN RETURN; END IF;
  SELECT t.id INTO alvo FROM plat.tenant t WHERE t.slug = p_slug;
  IF alvo IS NULL OR alvo = ctx THEN RETURN; END IF;   -- slug inexistente segue: a função devolve 0 linhas
  IF EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = ctx AND t.slug = 'plataforma') THEN RETURN; END IF;
  RAISE EXCEPTION 'contexto_de_outro_inquilino'
    USING HINT = 'a função exige o contexto do inquilino do slug';
END $$;

CREATE OR REPLACE FUNCTION plat.so_manutencao(p_o_que text) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ctx int := plat.tenant_atual();
BEGIN
  IF ctx IS NULL THEN RETURN; END IF;
  IF EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = ctx AND t.slug = 'plataforma') THEN RETURN; END IF;
  RAISE EXCEPTION '% só roda sem contexto de inquilino ou sob o inquilino técnico plataforma', p_o_que
    USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE OR REPLACE FUNCTION plat.argumento_no_minimo(p_valor int, p_min int, p_nome text) RETURNS int
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF p_valor IS NULL OR p_valor < p_min THEN
    RAISE EXCEPTION 'argumento_invalido' USING DETAIL = format('%s = %s; o mínimo é %s', p_nome, p_valor, p_min);
  END IF;
  RETURN p_valor;
END $$;

-- ---------------------------------------------------------------- 2. fura o isolamento: catálogo

-- G2-1/G2-2: no contexto do inquilino A, apagava versões de item do inquilino B. Agora só apaga item do
-- inquilino do contexto (ou de qualquer um sob `plataforma`, como plat.item_expurgar da 011).
CREATE OR REPLACE FUNCTION plat.item_versoes_compactar(p_item uuid, p_manter int DEFAULT 50) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE corte int; removidas int := 0; r record; n int; t_ctx int := plat.tenant_atual(); t_plataforma boolean;
BEGIN
  PERFORM plat.argumento_no_minimo(p_manter, 1, 'p_manter');
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = p_item AND (t_plataforma OR i.tenant_id = t_ctx)) THEN
    RETURN 0;   -- item de outro inquilino (ou inexistente): nada a fazer, sem revelar qual dos dois
  END IF;
  SELECT versao INTO corte FROM plat.item_versao WHERE item_id = p_item ORDER BY versao DESC OFFSET p_manter LIMIT 1;
  IF corte IS NULL THEN RETURN 0; END IF;
  FOR r IN SELECT array_agg(versao ORDER BY versao) AS vs, max(versao) AS topo,
                  sum(greatest(compactou, 1))::int AS resumidas
           FROM (SELECT versao, compactou, (row_number() OVER (ORDER BY versao) - 1) / 10 AS grupo
                 FROM plat.item_versao WHERE item_id = p_item AND versao <= corte) x
           GROUP BY grupo HAVING count(*) > 1 LOOP
    DELETE FROM plat.item_versao WHERE item_id = p_item AND versao = ANY (r.vs) AND versao <> r.topo;
    GET DIAGNOSTICS n = ROW_COUNT;
    removidas := removidas + n;
    UPDATE plat.item_versao SET rotulo = 'compactada', compactou = r.resumidas WHERE item_id = p_item AND versao = r.topo;
  END LOOP;
  RETURN removidas;
END $$;

CREATE OR REPLACE FUNCTION plat.itens_com_versoes_acima(p_manter int DEFAULT 50) RETURNS SETOF uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  PERFORM plat.argumento_no_minimo(p_manter, 1, 'p_manter');
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY SELECT v.item_id FROM plat.item_versao v WHERE (t_plataforma OR v.tenant_id = t_ctx)
               GROUP BY v.item_id HAVING count(*) > p_manter;
END $$;

-- item_contagens filtra por plat.pode_ler; a versão em lote da 019 não filtrava e devolvia as contagens de
-- item de QUALQUER inquilino. O remédio aqui é o filtro de INQUILINO, não plat.pode_ler por id: medido nesta
-- base, pode_ler por id custa 30-36 ms para 50 ids contra 2,6-3,0 ms do EXISTS por chave primária, e o motivo
-- de a função em lote existir (comentário da 019 em app/catalogo/comum.py) é justamente não pagar N consultas.
-- Fica escrito o que ela NÃO faz: a permissão de leitura DENTRO do inquilino continua sendo do chamador, que
-- só passa ids que já leu sob a RLS (app/catalogo/rotas_itens.py::carregar_varios, sempre autenticado).
-- Mantém uma linha por id pedido (o chamador indexa por id) e zera a contagem do que é de outro inquilino.
CREATE OR REPLACE FUNCTION plat.item_contagens_lote(p_itens uuid[])
RETURNS TABLE(item_id uuid, usado_por int, criado_a_partir_de int, grupos int, links_ativos int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT x.id,
         CASE WHEN x.ok THEN coalesce(up.n, 0) ELSE 0 END::int,
         CASE WHEN x.ok THEN coalesce(cp.n, 0) ELSE 0 END::int,
         CASE WHEN x.ok THEN coalesce(gr.n, 0) ELSE 0 END::int,
         CASE WHEN x.ok THEN coalesce(lk.n, 0) ELSE 0 END::int
  FROM (SELECT u.id, EXISTS (SELECT 1 FROM plat.item i
                             WHERE i.id = u.id AND i.tenant_id = plat.tenant_atual()) AS ok
        FROM unnest(p_itens) AS u(id)) AS x
  LEFT JOIN (
    SELECT r.destino AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL
    WHERE r.destino = ANY (p_itens) GROUP BY r.destino
  ) up ON up.id = x.id
  LEFT JOIN (
    SELECT r.origem AS id, count(*) AS n
    FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL
    WHERE r.origem = ANY (p_itens) GROUP BY r.origem
  ) cp ON cp.id = x.id
  LEFT JOIN (
    SELECT ig.item_id AS id, count(*) AS n FROM plat.item_grupo ig
    WHERE ig.item_id = ANY (p_itens) GROUP BY ig.item_id
  ) gr ON gr.id = x.id
  LEFT JOIN (
    SELECT k.item_id AS id, count(*) AS n FROM plat.compartilhamento_link k
    WHERE k.item_id = ANY (p_itens) AND k.revogado_em IS NULL AND (k.expira_em IS NULL OR k.expira_em > now())
    GROUP BY k.item_id
  ) lk ON lk.id = x.id;
$$;

CREATE OR REPLACE FUNCTION plat.catalogo_uso(p_tenant int)
RETURNS TABLE(itens bigint, na_lixeira bigint, bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*) FILTER (WHERE apagado_em IS NULL), count(*) FILTER (WHERE apagado_em IS NOT NULL),
         coalesce(sum(tamanho_bytes), 0)::bigint
  FROM plat.item WHERE tenant_id = plat.inquilino_do_argumento(p_tenant);
$$;

CREATE OR REPLACE FUNCTION plat.lixeira_expurgar(p_dias int DEFAULT 30, p_agora timestamptz DEFAULT now(),
                                                 p_ids uuid[] DEFAULT NULL)
RETURNS TABLE(item_id uuid, tenant_id int, tipo text, dados jsonb, miniatura_chave text, tamanho_bytes bigint, titulo text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  PERFORM plat.argumento_no_minimo(p_dias, 0, 'p_dias');
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY
    SELECT i.id, i.tenant_id, i.tipo, i.dados, i.miniatura_chave, i.tamanho_bytes, i.titulo
    FROM plat.item i
    WHERE i.apagado_em IS NOT NULL AND i.apagado_em < p_agora - make_interval(days => p_dias)
      AND (t_plataforma OR i.tenant_id = t_ctx)
      AND (p_ids IS NULL OR i.id = ANY (p_ids))
    ORDER BY i.apagado_em;
END $$;

-- ---------------------------------------------------------------- 3. fura o isolamento: bucket de objetos
-- Devolviam o SEGREDO S3 de escrita (chave_rw_segredo) de qualquer inquilino a partir do argumento.

CREATE OR REPLACE FUNCTION plat.arquivo_bucket_por_tenant(p_tenant_id int)
RETURNS TABLE(tenant_id int, bucket_id text, bucket_alias text, chave_rw_id text, chave_rw_segredo text,
              chave_ro_id text, chave_ro_segredo text, cota_bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
         b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes
  FROM plat.arquivo_bucket b WHERE b.tenant_id = plat.inquilino_do_argumento(p_tenant_id);
$$;

CREATE OR REPLACE FUNCTION plat.arquivo_bucket_resolver(p_slug text)
RETURNS TABLE(tenant_id int, bucket_id text, bucket_alias text, chave_rw_id text, chave_rw_segredo text,
              chave_ro_id text, chave_ro_segredo text, cota_bytes bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  -- a rota anônima de entrega roda SEM contexto (app/objetos.py::_resolver_bucket_por_slug): ali passa.
  PERFORM plat.inquilino_do_slug(p_slug);
  RETURN QUERY
    SELECT b.tenant_id, b.bucket_id, b.bucket_alias, b.chave_rw_id, b.chave_rw_segredo,
           b.chave_ro_id, b.chave_ro_segredo, b.cota_bytes
    FROM plat.arquivo_bucket b JOIN plat.tenant t ON t.id = b.tenant_id
    WHERE t.slug = p_slug;
END $$;

CREATE OR REPLACE FUNCTION plat.arquivo_bucket_cota_atualizar(p_tenant_id int, p_cota_bytes bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_cota_bytes IS NULL OR p_cota_bytes < 0 THEN RAISE EXCEPTION 'argumento_invalido'
    USING DETAIL = 'p_cota_bytes não pode ser nulo nem negativo'; END IF;
  UPDATE plat.arquivo_bucket SET cota_bytes = p_cota_bytes, atualizado_em = now()
   WHERE tenant_id = plat.inquilino_do_argumento(p_tenant_id);
END $$;

-- plat.arquivo_bucket_cotas_atualizar(int, bigint, bigint, boolean) NÃO entra aqui: não existe no master.
-- Ela está no schema `plat` de PRODUÇÃO porque uma trilha aplicou migração de ramo ainda não juntado
-- (medido em 06/09/2026, junto com cinco funções amc_* e duas colunas a mais em arquivo_bucket). Quem
-- juntar aquele ramo aplica a mesma guarda `plat.inquilino_do_argumento` nela; ver o handoff.

CREATE OR REPLACE FUNCTION plat.arquivo_bucket_registrar(p_tenant_id int, p_bucket_id text, p_bucket_alias text,
  p_chave_rw_id text, p_chave_rw_segredo text, p_chave_ro_id text, p_chave_ro_segredo text, p_cota_bytes bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_cota_bytes IS NULL OR p_cota_bytes < 0 THEN RAISE EXCEPTION 'argumento_invalido'
    USING DETAIL = 'p_cota_bytes não pode ser nulo nem negativo'; END IF;
  INSERT INTO plat.arquivo_bucket
    (tenant_id, bucket_id, bucket_alias, chave_rw_id, chave_rw_segredo, chave_ro_id, chave_ro_segredo, cota_bytes)
  VALUES (plat.inquilino_do_argumento(p_tenant_id), p_bucket_id, p_bucket_alias, p_chave_rw_id, p_chave_rw_segredo,
          p_chave_ro_id, p_chave_ro_segredo, p_cota_bytes)
  ON CONFLICT (tenant_id) DO NOTHING;
END $$;

-- ---------------------------------------------------------------- 4. fura o isolamento: identidade e LDAP

CREATE OR REPLACE FUNCTION plat.usuarios_ativos(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*)::int FROM plat.usuario WHERE tenant_id = plat.inquilino_do_argumento(p_tenant) AND ativo;
$$;

CREATE OR REPLACE FUNCTION plat.ldap_provisionar(p_tenant_id int, p_login text, p_nome text, p_email text,
  p_perfil text, p_sujeito_externo text, p_ativo boolean DEFAULT true)
RETURNS TABLE(criado boolean, perfil_anterior text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE existente record; alvo int;
BEGIN
  alvo := plat.inquilino_do_argumento(p_tenant_id);
  SELECT id, origem, perfil INTO existente FROM plat.usuario WHERE tenant_id = alvo AND login = lower(p_login);
  IF existente.id IS NOT NULL AND existente.origem <> 'ldap' THEN
    RAISE EXCEPTION 'login_em_uso_local';
  END IF;
  IF existente.id IS NULL THEN
    INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
    VALUES (alvo, lower(p_login), p_nome, p_email, p_perfil, 'ldap', p_sujeito_externo, p_ativo, NULL);
    RETURN QUERY SELECT true, NULL::text;
  ELSE
    UPDATE plat.usuario SET nome = p_nome, email = coalesce(p_email, email), perfil = p_perfil,
      sujeito_externo = p_sujeito_externo, ativo = p_ativo
    WHERE id = existente.id;
    RETURN QUERY SELECT false, existente.perfil;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION plat.ldap_importar_lote(p_tenant_id int, p_usuarios jsonb, p_perfil text)
RETURNS TABLE(criados int, ja_existentes int, recusados int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE u jsonb; n_criados int := 0; n_existentes int := 0; n_recusados int := 0; existente record; alvo int;
BEGIN
  alvo := plat.inquilino_do_argumento(p_tenant_id);
  IF jsonb_typeof(p_usuarios) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'argumento_invalido' USING DETAIL = 'p_usuarios precisa ser um array json';
  END IF;
  IF jsonb_array_length(p_usuarios) > 20000 THEN
    RAISE EXCEPTION 'argumento_invalido' USING DETAIL = 'p_usuarios acima de 20000 entradas';
  END IF;
  FOR u IN SELECT * FROM jsonb_array_elements(p_usuarios) LOOP
    SELECT id, origem INTO existente FROM plat.usuario WHERE tenant_id = alvo AND login = lower(u->>'login');
    IF existente.id IS NOT NULL AND existente.origem <> 'ldap' THEN
      n_recusados := n_recusados + 1;
    ELSIF existente.id IS NOT NULL THEN
      n_existentes := n_existentes + 1;
    ELSE
      INSERT INTO plat.usuario(tenant_id, login, nome, email, perfil, origem, sujeito_externo, ativo, senha_hash)
      VALUES (alvo, lower(u->>'login'), u->>'nome', u->>'email', p_perfil, 'ldap', u->>'sujeito_externo', false, NULL);
      n_criados := n_criados + 1;
    END IF;
  END LOOP;
  RETURN QUERY SELECT n_criados, n_existentes, n_recusados;
END $$;

-- provedor_ldap_de devolve bind_senha_cifrada: a rota de login roda SEM contexto e passa; um inquilino
-- autenticado pedindo o provedor de OUTRO slug, não.
CREATE OR REPLACE FUNCTION plat.provedor_ldap_de(p_tenant text)
RETURNS TABLE(tenant_id int, tenant_ativo boolean, tenant_slug text, tenant_nome text, config jsonb,
              habilitado boolean, url text, base_dn text, start_tls boolean, bind_dn text, bind_senha_cifrada text,
              filtro_usuario text, atributo_grupos text, perfil_padrao text, mapa_grupo_perfil jsonb)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.inquilino_do_slug(p_tenant);
  RETURN QUERY
    SELECT t.id, t.ativo, t.slug, t.nome, t.config, pl.habilitado, pl.url, pl.base_dn, pl.start_tls, pl.bind_dn,
           pl.bind_senha_cifrada, pl.filtro_usuario, pl.atributo_grupos, pl.perfil_padrao, pl.mapa_grupo_perfil
    FROM plat.tenant t LEFT JOIN plat.provedor_ldap pl ON pl.tenant_id = t.id
    WHERE t.slug = p_tenant;
END $$;

-- ---------------------------------------------------------------- 5. fura o isolamento: cotas e configuração
-- Leem tenant.config de qualquer inquilino a partir do argumento. Chamadas do worker (job_pegar, jobs_no_dia)
-- rodam SEM contexto e continuam passando.

CREATE OR REPLACE FUNCTION plat.cota_usuarios(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_usuarios')::int, 2000) FROM plat.tenant WHERE id = plat.inquilino_do_argumento(p_tenant); $$;

CREATE OR REPLACE FUNCTION plat.cota_itens(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->'catalogo'->>'cota_itens')::int, 100000) FROM plat.tenant WHERE id = plat.inquilino_do_argumento(p_tenant); $$;

CREATE OR REPLACE FUNCTION plat.cota_agendas(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_agendas')::int, 50) FROM plat.tenant WHERE id = plat.inquilino_do_argumento(p_tenant); $$;

CREATE OR REPLACE FUNCTION plat.categorias_max(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT least(900, greatest(50, coalesce((config->'catalogo'->>'categorias_max')::int, 200)))
  FROM plat.tenant WHERE id = plat.inquilino_do_argumento(p_tenant); $$;

-- ---------------------------------------------------------------- 6. destrutiva sem validação

-- G4-10: `plat.evento_expurgar(-1)` derrubava a partição do mês corrente e zerava a auditoria de todos os
-- inquilinos. Agora: só manutenção (sem contexto ou `plataforma`) e p_meses >= 1.
CREATE OR REPLACE FUNCTION plat.evento_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date;
BEGIN
  PERFORM plat.so_manutencao('plat.evento_expurgar');
  PERFORM plat.argumento_no_minimo(p_meses, 1, 'p_meses');
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.evento'::regclass LOOP
    IF r.relname ~ 'y\d{4}m\d{2}$'
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.log_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date;
BEGIN
  PERFORM plat.so_manutencao('plat.log_expurgar');
  PERFORM plat.argumento_no_minimo(p_meses, 1, 'p_meses');
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.log_acesso'::regclass LOOP
    IF r.relname ~ 'y\d{4}m\d{2}$'
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

-- apaga sessão de todos os inquilinos: admin de inquilino não enfileira mais este periódico com efeito
CREATE OR REPLACE FUNCTION plat.sessoes_expurgar() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  PERFORM plat.so_manutencao('plat.sessoes_expurgar');
  DELETE FROM plat.sessao WHERE expira_em < now() OR coalesce(ultimo_uso, criado_em) < now() - interval '24 hours';
  GET DIAGNOSTICS n = ROW_COUNT;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL
  WHERE desafio_2fa_ate IS NOT NULL AND desafio_2fa_ate < now();
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.jobs_expurgar(p_dias_job int, p_dias_log int)
RETURNS TABLE(jobs_apagados int, logs_apagados int, marcadores_apagados int, passos_apagados int, rodando uuid[])
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, plat_trabalho, public AS $$
DECLARE nj int; nl int; nm int; np int;
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT id FROM plat.tenant WHERE slug = 'plataforma') THEN
    RAISE EXCEPTION 'expurgo só no contexto do inquilino técnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  PERFORM plat.argumento_no_minimo(p_dias_job, 1, 'p_dias_job');
  PERFORM plat.argumento_no_minimo(p_dias_log, 1, 'p_dias_log');
  DELETE FROM plat.job_log WHERE em < now() - make_interval(days => p_dias_log);
  GET DIAGNOSTICS nl = ROW_COUNT;
  DELETE FROM plat.job WHERE estado IN ('concluido','falhou','cancelado') AND terminado_em < now() - make_interval(days => p_dias_job);
  GET DIAGNOSTICS nj = ROW_COUNT;
  DELETE FROM plat_trabalho.marcadores m WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = m.job_id);
  GET DIAGNOSTICS nm = ROW_COUNT;
  DELETE FROM plat_trabalho.passos p WHERE NOT EXISTS (SELECT 1 FROM plat.job j WHERE j.id = p.job_id AND j.estado = 'rodando');
  GET DIAGNOSTICS np = ROW_COUNT;
  RETURN QUERY SELECT nj, nl, nm, np, coalesce((SELECT array_agg(id) FROM plat.job WHERE estado = 'rodando'), '{}'::uuid[]);
END $$;

CREATE OR REPLACE FUNCTION plat.uploads_expirar_candidatos(p_horas int)
RETURNS TABLE(id uuid, tenant_id int, usuario_id int, upload_s3_id text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.so_manutencao('plat.uploads_expirar_candidatos');
  PERFORM plat.argumento_no_minimo(p_horas, 1, 'p_horas');
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.usuario_id, u.upload_s3_id
    FROM plat.upload u
    WHERE u.estado = 'iniciado' AND u.atualizado_em < now() - make_interval(hours => p_horas)
    ORDER BY u.atualizado_em;
END $$;

CREATE OR REPLACE FUNCTION plat.worker_ceifar(p_limite_s int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  PERFORM plat.argumento_no_minimo(p_limite_s, 1, 'p_limite_s');
  DELETE FROM plat.worker WHERE heartbeat_em < now() - make_interval(secs => p_limite_s);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.job_ceifar(p_limite_s int, p_max_reinicios int DEFAULT 5) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0;
BEGIN
  PERFORM plat.argumento_no_minimo(p_limite_s, 1, 'p_limite_s');
  PERFORM plat.argumento_no_minimo(p_max_reinicios, 1, 'p_max_reinicios');
  FOR r IN SELECT j.id, j.worker FROM plat.job j
           WHERE j.estado = 'rodando'
             AND coalesce(j.heartbeat_em, j.iniciado_em) < now() - make_interval(secs => p_limite_s)
             AND NOT EXISTS (SELECT 1 FROM plat.worker w WHERE w.nome = j.worker
                             AND w.heartbeat_em >= now() - make_interval(secs => p_limite_s)) LOOP
    PERFORM plat.job_devolver(r.id, r.worker, 'worker sem sinal', false, 0, p_max_reinicios);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.conexao_saude_registrar(p_id uuid, p_ok boolean, p_status int, p_mensagem text,
                                                        p_latencia_ms int, p_manter int DEFAULT 30) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int; v_saude text; v_atual int;
BEGIN
  PERFORM plat.argumento_no_minimo(p_manter, 1, 'p_manter');
  SELECT tenant_id INTO v_tenant FROM plat.conexao WHERE id = p_id;
  IF v_tenant IS NULL THEN RETURN; END IF;
  v_atual := plat.tenant_atual();
  IF v_atual IS DISTINCT FROM v_tenant
     AND v_atual IS DISTINCT FROM (SELECT t.id FROM plat.tenant t WHERE t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'sem permissao para registrar a saude desta conexao' USING ERRCODE = 'insufficient_privilege';
  END IF;
  v_saude := CASE WHEN p_ok THEN 'ok' ELSE 'erro' END;
  UPDATE plat.conexao
     SET saude = v_saude, saude_mensagem = p_mensagem, saude_latencia_ms = p_latencia_ms, saude_verificada_em = now()
   WHERE id = p_id;
  INSERT INTO plat.conexao_saude_historico(conexao_id, tenant_id, ok, status, mensagem, latencia_ms)
  VALUES (p_id, v_tenant, p_ok, p_status, p_mensagem, p_latencia_ms);
  DELETE FROM plat.conexao_saude_historico
   WHERE conexao_id = p_id
     AND id NOT IN (
       SELECT id FROM plat.conexao_saude_historico WHERE conexao_id = p_id ORDER BY verificada_em DESC LIMIT p_manter
     );
END $$;

-- partição fora de uma janela plausível é tabela lixo criada a pedido do chamador
CREATE OR REPLACE FUNCTION plat.evento_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date; fim date; nome text;
BEGIN
  IF p_mes IS NULL OR p_mes < (now() - interval '10 years')::date OR p_mes > (now() + interval '2 years')::date THEN
    RAISE EXCEPTION 'argumento_invalido' USING DETAIL = 'p_mes fora da janela de 10 anos atrás a 2 anos à frente';
  END IF;
  ini := date_trunc('month', p_mes)::date;
  fim := (ini + interval '1 month')::date;
  nome := format('evento_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.evento FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
  END IF;
  RETURN nome;
END $$;

CREATE OR REPLACE FUNCTION plat.log_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date; fim date; nome text;
BEGIN
  IF p_mes IS NULL OR p_mes < (now() - interval '10 years')::date OR p_mes > (now() + interval '2 years')::date THEN
    RAISE EXCEPTION 'argumento_invalido' USING DETAIL = 'p_mes fora da janela de 10 anos atrás a 2 anos à frente';
  END IF;
  ini := date_trunc('month', p_mes)::date;
  fim := (ini + interval '1 month')::date;
  nome := format('log_acesso_y%sm%s', to_char(ini, 'YYYY'), to_char(ini, 'MM'));
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.log_acesso FOR VALUES FROM (%L) TO (%L)', nome, ini, fim);
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
    EXECUTE format('CREATE POLICY p_%s ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', nome, nome);
  END IF;
  RETURN nome;
END $$;

-- ---------------------------------------------------------------- 7. permissões

DO $$
DECLARE f text;
BEGIN
  -- as três funções que ainda tinham EXECUTE para PUBLIC (030 e 046 não repetiram o REVOKE da 011)
  FOREACH f IN ARRAY ARRAY['plat.tg_conexao_atualizado_em()', 'plat.upload_reservado_bytes(int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
  END LOOP;
  REVOKE EXECUTE ON FUNCTION plat.tg_conexao_atualizado_em() FROM plat_app;  -- função de gatilho
  REVOKE EXECUTE ON FUNCTION plat.uploads_expirar_candidatos(int) FROM PUBLIC;
  GRANT EXECUTE ON FUNCTION plat.uploads_expirar_candidatos(int) TO plat_app;
  GRANT EXECUTE ON FUNCTION plat.upload_reservado_bytes(int) TO plat_app;

  -- guardas novas: o app precisa executá-las porque as funções que as chamam são SECURITY DEFINER do dono,
  -- mas o REVOKE de PUBLIC vale para todas
  FOREACH f IN ARRAY ARRAY['plat.inquilino_do_argumento(int)', 'plat.inquilino_do_slug(text)',
                           'plat.so_manutencao(text)', 'plat.argumento_no_minimo(int, int, text)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;

  -- reafirma a 009: apagar inquilino inteiro nunca sai de plat_app; só plat.tenant_apagar (com sessão de
  -- superadmin) chega lá. Em produção o EXECUTE de plat_app tinha voltado (medido em 06/09/2026).
  REVOKE EXECUTE ON FUNCTION plat.tenant_apagar_interno(int) FROM PUBLIC, plat_app;

  -- agenda_registrar_fim escreve em plat.agenda de qualquer inquilino por id; só o worker a chama
  -- (plat.job_terminar, plat.job_devolver), nunca a API
  REVOKE EXECUTE ON FUNCTION plat.agenda_registrar_fim(uuid, uuid, text) FROM PUBLIC, plat_app;
  GRANT EXECUTE ON FUNCTION plat.agenda_registrar_fim(uuid, uuid, text) TO plat_worker;

  -- reafirmação idempotente das seis que a 047 deixou com PUBLIC (laudo ataque-g1-ADVERSARIO.md). A 048 e a
  -- 049 já as fecharam em 06/09 15:35 e 15:46 UTC; ficam aqui para que uma base restaurada de antes disso, ou
  -- reconstruída fora de ordem, não volte a expor convite/redefinição a todo papel do banco compartilhado.
  FOREACH f IN ARRAY ARRAY[
    'plat.convite_resolver(text)', 'plat.convite_aceitar(text, text, text, text)',
    'plat.redefinicao_solicitar(text, text, text, int, int, int)', 'plat.redefinicao_resolver(text)',
    'plat.redefinicao_contexto(text)', 'plat.redefinicao_marcar_usada(text, int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
