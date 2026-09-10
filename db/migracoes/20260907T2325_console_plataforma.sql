-- 20260907T2325_console_plataforma: item L0-07-f-console-plataforma (console do superadmin, rota /plataforma).
-- O console mínimo da 003/029 (listar, criar, suspender, reativar, apagar) ganha o que faltava para operar um
-- portal com N inquilinos: uso por inquilino na listagem, cotas alteráveis pelo operador, criação já com cotas,
-- suspensão com mensagem para os membros (503 com a mensagem, dado intacto), desligamento forçado do 2FA de um
-- administrador de inquilino, fila de jobs agregada e a trilha de eventos da própria plataforma.
--
-- Regras que continuam (ADR 0002 seção 10): o superadmin é resolvido SEMPRE pelo hash da sessão
-- (plat.plataforma_operador), nunca por GUC nem por cookie forjado; toda função abaixo é SECURITY DEFINER e
-- começa por essa checagem; plat_app só executa, nunca lê plat.tenant de outro inquilino direto.
-- Nada aqui toca uma migração aplicada: as funções da 003/029 que mudam de corpo mantêm a assinatura.

-- ---------------------------------------------------------------- vocabulário de eventos (append, reaplicável)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('inquilinos/cotas', 'cotas do inquilino alteradas pelo operador da plataforma'),
  ('inquilinos/2fa_desligar', 'segundo fator de um administrador do inquilino desligado pelo operador da plataforma')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- slugs reservados em UM lugar
-- A lista da tenant_criar (003/029) estava inscrita no corpo da função; passa a viver aqui e inclui os caminhos
-- de página da raiz (app/paginas.py), para um inquilino nunca colidir com uma rota da própria plataforma.
-- O codinome do produto entra como left('plataforma', 4): a base de trilha (laco/trilha_reescrever.py) reescreve o
-- token literal do schema em todo SQL, e na 029 isso deixava exatamente esse slug SEM reserva nas bases de teste.
CREATE OR REPLACE FUNCTION plat.slug_reservado(p_slug text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT p_slug = left('plataforma', 4)
      OR p_slug IN ('plataforma', 'public', 'admin', 'api', 'static', 'svc', 'ogc', 'tiles', 'saude',
                    'entrar', 'conta', 'rest', 'conteudo', 'mapa', 'conexoes', 'uploads', 'construtor', 'executar',
                    'tarefas', 'aceitar-convite', 'redefinir-senha', 'postgres', 'pg-catalog', 'information-schema')
$$;

-- ---------------------------------------------------------------- cotas: aplica um jsonb de cotas ao config
-- Chaves aceitas (as mesmas que as funções cota_* da 004/011/034 já leem): cota_usuarios, cota_jobs_dia,
-- cota_jobs_simultaneos, cota_agendas (raiz do config) e cota_itens (config.catalogo). Chave ausente = mantém.
CREATE OR REPLACE FUNCTION plat.cotas_aplicar(p_config jsonb, p_cotas jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE c jsonb := coalesce(p_config, '{}'::jsonb); k text;
BEGIN
  IF p_cotas IS NULL THEN RETURN c; END IF;
  FOREACH k IN ARRAY ARRAY['cota_usuarios', 'cota_jobs_dia', 'cota_jobs_simultaneos', 'cota_agendas'] LOOP
    IF p_cotas ? k AND p_cotas->>k IS NOT NULL THEN
      c := c || jsonb_build_object(k, (p_cotas->>k)::int);
    END IF;
  END LOOP;
  IF p_cotas ? 'cota_itens' AND p_cotas->>'cota_itens' IS NOT NULL THEN
    c := c || jsonb_build_object('catalogo', coalesce(c->'catalogo', '{}'::jsonb)
                                              || jsonb_build_object('cota_itens', (p_cotas->>'cota_itens')::int));
  END IF;
  RETURN c;
END $$;

-- ---------------------------------------------------------------- criar com cotas (assinatura nova, 9 argumentos)
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text, p_cota_bytes bigint, p_cotas jsonb)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int; uid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF plat.slug_reservado(p_slug) THEN
    RAISE EXCEPTION 'slug_reservado';
  END IF;
  INSERT INTO plat.tenant(slug, nome, config, cota_bytes)
  VALUES (p_slug, p_nome, plat.cotas_aplicar(coalesce(p_config, '{}'::jsonb), p_cotas),
          coalesce(p_cota_bytes, 21474836480))
  RETURNING id INTO tid;
  INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, trocar_senha)
  VALUES (tid, lower(p_admin_login), p_admin_nome, p_senha_hash, 'admin', true) RETURNING id INTO uid;
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', 'd_' || p_slug);  -- item L0-04
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', 'd_' || p_slug);
  RETURN QUERY SELECT tid, uid;
END $$;

-- a assinatura da 003/029 (7 argumentos) continua existindo e delega: cota padrão, sem cotas extras
CREATE OR REPLACE FUNCTION plat.tenant_criar(p_sessao_hash text, p_slug text, p_nome text, p_config jsonb,
  p_admin_login text, p_admin_nome text, p_senha_hash text)
RETURNS TABLE (tenant_id int, usuario_id int) LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT * FROM plat.tenant_criar(p_sessao_hash, p_slug, p_nome, p_config, p_admin_login, p_admin_nome,
                                  p_senha_hash, NULL::bigint, NULL::jsonb)
$$;

-- ---------------------------------------------------------------- alterar cotas
CREATE OR REPLACE FUNCTION plat.tenant_cotas_alterar(p_sessao_hash text, p_id int, p_cota_bytes bigint, p_cotas jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_id) THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  UPDATE plat.tenant
     SET cota_bytes = coalesce(p_cota_bytes, cota_bytes),
         config = plat.cotas_aplicar(config, p_cotas)
   WHERE id = p_id;
  IF p_cota_bytes IS NOT NULL THEN
    PERFORM plat.arquivo_bucket_cota_atualizar(p_id, p_cota_bytes);  -- 022: bucket já criado acompanha
  END IF;
END $$;

-- ---------------------------------------------------------------- suspender com mensagem para os membros
-- A mensagem fica em config.suspensao {mensagem, em}; reativar apaga a chave. Sessões e tokens NÃO são apagados
-- (dado intacto): auth_sessao/auth_token já recusam enquanto t.ativo = false, e credencial_suspensa (abaixo)
-- permite à API responder 503 com a mensagem em vez de um 401 mudo.
CREATE OR REPLACE FUNCTION plat.tenant_suspender(p_sessao_hash text, p_id int, p_ativo boolean, p_mensagem text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' AND NOT p_ativo THEN RAISE EXCEPTION 'plataforma_nao_suspende'; END IF;
  UPDATE plat.tenant
     SET ativo = p_ativo,
         config = CASE WHEN p_ativo THEN config - 'suspensao'
                       ELSE config || jsonb_build_object('suspensao', jsonb_strip_nulls(
                              jsonb_build_object('mensagem', nullif(btrim(coalesce(p_mensagem, '')), ''), 'em', now())))
                  END
   WHERE id = p_id;
END $$;

-- a assinatura da 003 (3 argumentos) delega, sem mensagem
CREATE OR REPLACE FUNCTION plat.tenant_suspender(p_sessao_hash text, p_id int, p_ativo boolean) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT plat.tenant_suspender(p_sessao_hash, p_id, p_ativo, NULL::text)
$$;

-- pré-contexto (o hash é o segredo): a credencial (sessão ou token) existe e só não autentica porque o
-- inquilino está suspenso? Devolve uma linha com a mensagem quando sim; nada quando não. Chamada só no caminho
-- de falha da autenticação, nunca no caminho quente.
CREATE OR REPLACE FUNCTION plat.credencial_suspensa(p_hash text)
RETURNS TABLE (mensagem text, desde timestamptz)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT t.config #>> '{suspensao,mensagem}', (t.config #>> '{suspensao,em}')::timestamptz
  FROM plat.sessao s JOIN plat.tenant t ON t.id = s.tenant_id
  WHERE s.token_hash = p_hash AND NOT t.ativo AND s.expira_em > now()
  UNION ALL
  SELECT t.config #>> '{suspensao,mensagem}', (t.config #>> '{suspensao,em}')::timestamptz
  FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE k.token_hash = p_hash AND NOT t.ativo AND k.revogado_em IS NULL
    AND (k.expira_em IS NULL OR k.expira_em > now())
  LIMIT 1
$$;

-- ---------------------------------------------------------------- listar com uso
-- tenant_listar (003) continua; esta devolve o que o console mostra por inquilino: usuários (total e ativos) e
-- cota, bytes registrados em plat.arquivo (022; o contador simétrico do L0-07-c substitui quando entrar) e cota,
-- itens vivos e cota, jobs pendentes/rodando, último acesso e a suspensão (mensagem, quando).
CREATE OR REPLACE FUNCTION plat.tenant_listar_uso(p_sessao_hash text)
RETURNS TABLE (id int, slug text, nome text, ativo boolean, usuarios bigint, usuarios_ativos bigint,
               cota_usuarios int, criado_em timestamptz, ultimo_acesso timestamptz, cota_bytes bigint,
               bytes_usados bigint, itens bigint, cota_itens int, jobs_pendentes bigint, jobs_rodando bigint,
               suspensao jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT t.id, t.slug, t.nome, t.ativo,
           (SELECT count(*) FROM plat.usuario u WHERE u.tenant_id = t.id),
           (SELECT count(*) FROM plat.usuario u WHERE u.tenant_id = t.id AND u.ativo),
           plat.cota_usuarios(t.id),
           t.criado_em,
           (SELECT max(u.ultimo_login) FROM plat.usuario u WHERE u.tenant_id = t.id),
           t.cota_bytes,
           (SELECT coalesce(sum(a.bytes), 0)::bigint FROM plat.arquivo a WHERE a.tenant_id = t.id AND a.apagado_em IS NULL),
           (SELECT count(*) FROM plat.item i WHERE i.tenant_id = t.id AND i.apagado_em IS NULL),
           plat.cota_itens(t.id),
           (SELECT count(*) FROM plat.job j WHERE j.tenant_id = t.id AND j.estado = 'pendente'),
           (SELECT count(*) FROM plat.job j WHERE j.tenant_id = t.id AND j.estado = 'rodando'),
           t.config->'suspensao'
    FROM plat.tenant t
    ORDER BY t.slug;
END $$;

-- ---------------------------------------------------------------- detalhe de um inquilino (cotas, uso, admins)
CREATE OR REPLACE FUNCTION plat.tenant_detalhe(p_sessao_hash text, p_id int) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; saida jsonb;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT * INTO r FROM plat.tenant_listar_uso(p_sessao_hash) x WHERE x.id = p_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  saida := jsonb_build_object(
    'id', r.id, 'slug', r.slug, 'nome', r.nome, 'ativo', r.ativo,
    'criado_em', r.criado_em, 'ultimo_acesso', r.ultimo_acesso, 'suspensao', r.suspensao,
    'cotas', jsonb_build_object(
      'cota_bytes', r.cota_bytes, 'cota_usuarios', r.cota_usuarios, 'cota_itens', r.cota_itens,
      'cota_jobs_dia', plat.cota_jobs_dia(p_id), 'cota_jobs_simultaneos', plat.cota_jobs_simultaneos(p_id),
      'cota_agendas', plat.cota_agendas(p_id)),
    'uso', jsonb_build_object(
      'usuarios', r.usuarios, 'usuarios_ativos', r.usuarios_ativos, 'bytes_usados', r.bytes_usados,
      'itens', r.itens, 'jobs_pendentes', r.jobs_pendentes, 'jobs_rodando', r.jobs_rodando,
      'jobs_hoje', plat.jobs_no_dia(p_id),
      'agendas', (SELECT count(*) FROM plat.agenda a WHERE a.tenant_id = p_id)),
    'admins', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'id', u.id, 'login', u.login, 'nome', u.nome, 'ativo', u.ativo, 'origem', u.origem,
                   'totp_ativo', u.totp_ativo, 'ultimo_login', u.ultimo_login) ORDER BY u.login), '[]'::jsonb)
               FROM plat.usuario u WHERE u.tenant_id = p_id AND u.perfil = 'admin'));
  RETURN saida;
END $$;

-- ---------------------------------------------------------------- 2FA de um admin de inquilino, desligado pelo operador
-- Só administradores (o membro comum tem o admin do próprio inquilino para isso: POST /api/usuarios/{id}/2fa/desativar);
-- nunca no inquilino `plataforma` (o 2FA do operador é obrigatório e não se desliga por aqui). Sessões do alvo caem.
CREATE OR REPLACE FUNCTION plat.tenant_admin_2fa_desligar(p_sessao_hash text, p_tenant int, p_usuario int)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant) THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant AND slug = 'plataforma') THEN
    RAISE EXCEPTION 'plataforma_2fa_obrigatorio';
  END IF;
  SELECT u.id, u.login, u.perfil INTO r FROM plat.usuario u WHERE u.id = p_usuario AND u.tenant_id = p_tenant;
  IF NOT FOUND THEN RAISE EXCEPTION 'usuario_de_outro_inquilino'; END IF;
  IF r.perfil <> 'admin' THEN RAISE EXCEPTION 'so_admin_de_inquilino'; END IF;
  UPDATE plat.usuario
     SET totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, codigos_recuperacao = NULL,
         desafio_2fa_hash = NULL, desafio_2fa_ate = NULL
   WHERE id = p_usuario;
  DELETE FROM plat.sessao WHERE usuario_id = p_usuario;
  RETURN r.login;
END $$;

-- ---------------------------------------------------------------- fila agregada (todos os inquilinos + workers)
CREATE OR REPLACE FUNCTION plat.plataforma_fila_resumo(p_sessao_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN jsonb_build_object(
    'total', (SELECT jsonb_build_object(
                'pendente', count(*) FILTER (WHERE estado = 'pendente'),
                'rodando', count(*) FILTER (WHERE estado = 'rodando'),
                'concluido_24h', count(*) FILTER (WHERE estado = 'concluido' AND terminado_em > now() - interval '24 hours'),
                'falhou_24h', count(*) FILTER (WHERE estado = 'falhou' AND terminado_em > now() - interval '24 hours'),
                'cancelado_24h', count(*) FILTER (WHERE estado = 'cancelado' AND terminado_em > now() - interval '24 hours'))
              FROM plat.job),
    'mais_antigo_pendente_em', (SELECT min(agendado_para) FROM plat.job WHERE estado = 'pendente' AND agendado_para <= now()),
    'por_inquilino', (SELECT coalesce(jsonb_agg(x ORDER BY x->>'slug'), '[]'::jsonb) FROM (
        SELECT jsonb_build_object(
                 'id', t.id, 'slug', t.slug,
                 'pendente', count(*) FILTER (WHERE j.estado = 'pendente'),
                 'rodando', count(*) FILTER (WHERE j.estado = 'rodando'),
                 'falhou_24h', count(*) FILTER (WHERE j.estado = 'falhou' AND j.terminado_em > now() - interval '24 hours'),
                 'concluido_24h', count(*) FILTER (WHERE j.estado = 'concluido' AND j.terminado_em > now() - interval '24 hours')) x
        FROM plat.tenant t JOIN plat.job j ON j.tenant_id = t.id
        GROUP BY t.id) q),
    'workers', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                  'nome', w.nome, 'processos', w.processos, 'rodando', w.rodando, 'heartbeat_em', w.heartbeat_em,
                  'vivo', w.heartbeat_em > now() - interval '2 minutes') ORDER BY w.nome), '[]'::jsonb)
                FROM plat.worker w));
END $$;

-- ---------------------------------------------------------------- eventos da plataforma (trilha do próprio console)
-- Só o inquilino `plataforma` (criar/suspender/reativar/apagar/cotas/2fa/leitura_superadmin...): a leitura de eventos
-- de OUTRO inquilino continua pelo caminho já auditado (GET /api/eventos com X-Plat-Inquilino, evento
-- inquilinos/leitura_superadmin), nunca por aqui.
CREATE OR REPLACE FUNCTION plat.plataforma_eventos(p_sessao_hash text, p_tipo text, p_limite int, p_deslocamento int)
RETURNS TABLE (total bigint, id bigint, em timestamptz, tipo text, ator_id int, ator_login text, alvo_tipo text,
               alvo_id text, propriedades jsonb, ip text, req_id text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT t.id INTO tid FROM plat.tenant t WHERE t.slug = 'plataforma';
  RETURN QUERY
    SELECT count(*) OVER () AS total, e.id, e.em, e.tipo, e.ator_id, u.login, e.alvo_tipo, e.alvo_id,
           e.propriedades, e.ip, e.req_id
    FROM plat.evento e LEFT JOIN plat.usuario u ON u.id = e.ator_id
    WHERE e.tenant_id = tid AND (p_tipo IS NULL OR e.tipo = p_tipo)
    ORDER BY e.em DESC, e.id DESC
    LIMIT greatest(p_limite, 1) OFFSET greatest(p_deslocamento, 0);
END $$;

-- ---------------------------------------------------------------- permissões (padrão da 003: só plat_app executa)
REVOKE EXECUTE ON FUNCTION plat.slug_reservado(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.cotas_aplicar(jsonb, jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_criar(text, text, text, jsonb, text, text, text, bigint, jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_criar(text, text, text, jsonb, text, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_cotas_alterar(text, int, bigint, jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_suspender(text, int, boolean, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_suspender(text, int, boolean) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.credencial_suspensa(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_listar_uso(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_detalhe(text, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tenant_admin_2fa_desligar(text, int, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.plataforma_fila_resumo(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.plataforma_eventos(text, text, int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.slug_reservado(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_criar(text, text, text, jsonb, text, text, text, bigint, jsonb) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_criar(text, text, text, jsonb, text, text, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_cotas_alterar(text, int, bigint, jsonb) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_suspender(text, int, boolean, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_suspender(text, int, boolean) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.credencial_suspensa(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_listar_uso(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_detalhe(text, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenant_admin_2fa_desligar(text, int, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.plataforma_fila_resumo(text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.plataforma_eventos(text, text, int, int) TO plat_app;
