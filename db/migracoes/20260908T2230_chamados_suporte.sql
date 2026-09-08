-- 20260908T2230_chamados_suporte: item L7-13-a-chamados. Chamados de suporte dentro do produto:
-- plat.chamado (com contexto automático e RLS por inquilino), plat.chamado_comentario (cliente × operador) e
-- plat.chamado_anexo (captura de tela e arquivos, bytes no Garage pela mesma classe de objetos do upload
-- retomável; a chave NUNCA sai daqui — o download só existe por rota de API com sessão). O painel do operador
-- (superadmin) lê e responde chamados de todos os inquilinos por funções SECURITY DEFINER resolvidas pelo hash
-- da sessão, o mesmo padrão de plat.tenant_listar (003): a RLS por inquilino fica de pé e o operador passa por
-- cima dela com a identidade provada dentro da função, nunca por GUC. Idempotente; sem BEGIN/COMMIT (padrão
-- das demais migrações desta linha).

CREATE TABLE IF NOT EXISTS plat.chamado (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             int NOT NULL REFERENCES plat.tenant(id),
  numero                int NOT NULL,                -- sequencial POR inquilino (o que o cliente cita)
  titulo                text NOT NULL,
  descricao             text NOT NULL,
  severidade            text NOT NULL CHECK (severidade IN ('baixa','media','alta','critica')),
  estado                text NOT NULL DEFAULT 'aberto'
                        CHECK (estado IN ('aberto','em_analise','aguardando_cliente','resolvido','fechado')),
  contexto              jsonb NOT NULL DEFAULT '{}', -- tela, versão, navegador, idioma, req_ids, estrutura do DOM
  aberto_por            int NOT NULL REFERENCES plat.usuario(id),
  aberto_em             timestamptz NOT NULL DEFAULT now(),
  primeira_resposta_em  timestamptz,                 -- 1ª ação do operador (comentário ou estado); base do SLA
  resolvido_em          timestamptz,
  fechado_em            timestamptz,
  fechado_por           int REFERENCES plat.usuario(id),
  visto_cliente_em      timestamptz,                 -- última vez que o cliente abriu o chamado (base do banner)
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, numero)
);
CREATE INDEX IF NOT EXISTS ix_chamado_tenant_em ON plat.chamado (tenant_id, aberto_em DESC);
CREATE INDEX IF NOT EXISTS ix_chamado_tenant_estado ON plat.chamado (tenant_id, estado);

CREATE TABLE IF NOT EXISTS plat.chamado_comentario (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  chamado_id  uuid NOT NULL REFERENCES plat.chamado(id) ON DELETE CASCADE,
  autor_id    int NOT NULL REFERENCES plat.usuario(id),
  origem      text NOT NULL CHECK (origem IN ('cliente','operador')),
  texto       text NOT NULL,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chamado_comentario_chamado ON plat.chamado_comentario (chamado_id, criado_em);

CREATE TABLE IF NOT EXISTS plat.chamado_anexo (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  chamado_id  uuid NOT NULL REFERENCES plat.chamado(id) ON DELETE CASCADE,
  nome        text NOT NULL,
  tipo        text NOT NULL,          -- tipo declarado, provado contra os bytes na entrada (app/uploads/tipos.py)
  bytes       int NOT NULL,
  sha256      text NOT NULL,
  chave       text NOT NULL,          -- chave no Garage; NUNCA devolvida por rota nenhuma
  enviado_por int REFERENCES plat.usuario(id),
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chamado_anexo_chamado ON plat.chamado_anexo (chamado_id, criado_em);

-- ---------------------------------------------------------------- RLS: o chamado é dado do inquilino
ALTER TABLE plat.chamado            ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.chamado_comentario ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.chamado_anexo      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_chamado ON plat.chamado;
CREATE POLICY p_chamado ON plat.chamado FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_chamado_comentario ON plat.chamado_comentario;
CREATE POLICY p_chamado_comentario ON plat.chamado_comentario FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_chamado_anexo ON plat.chamado_anexo;
CREATE POLICY p_chamado_anexo ON plat.chamado_anexo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- operador (superadmin): SECURITY DEFINER
-- Mesmo padrão de plat.tenant_listar/plat.plataforma_operador (003): a identidade do superadmin é provada
-- DENTRO da função pelo hash da sessão; plat_app nunca ganha privilégio direto de leitura fora de contexto.

CREATE OR REPLACE FUNCTION plat.chamado_fila_operador(p_sessao_hash text, p_estado text DEFAULT NULL)
RETURNS TABLE (s_id uuid, s_tenant_id int, s_tenant_slug text, s_numero int, s_titulo text, s_severidade text,
               s_estado text, s_aberto_por text, s_aberto_em timestamptz, s_primeira_resposta_em timestamptz,
               s_atualizado_em timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT c.id, c.tenant_id, t.slug, c.numero, c.titulo, c.severidade, c.estado, u.login,
           c.aberto_em, c.primeira_resposta_em, c.atualizado_em
    FROM plat.chamado c
    JOIN plat.tenant t ON t.id = c.tenant_id
    JOIN plat.usuario u ON u.id = c.aberto_por
    WHERE p_estado IS NULL OR c.estado = p_estado
    ORDER BY c.aberto_em DESC
    LIMIT 500;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_ver(p_sessao_hash text, p_id uuid)
RETURNS TABLE (s_id uuid, s_tenant_id int, s_tenant_slug text, s_numero int, s_titulo text, s_descricao text,
               s_severidade text, s_estado text, s_contexto jsonb, s_aberto_por text, s_aberto_por_email text,
               s_aberto_por_idioma text, s_aberto_em timestamptz, s_primeira_resposta_em timestamptz,
               s_resolvido_em timestamptz, s_fechado_em timestamptz, s_atualizado_em timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v uuid;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT c.id INTO v FROM plat.chamado c WHERE c.id = p_id;
  IF v IS NULL THEN RAISE EXCEPTION 'chamado_inexistente'; END IF;
  RETURN QUERY
    SELECT c.id, c.tenant_id, t.slug, c.numero, c.titulo, c.descricao, c.severidade, c.estado, c.contexto,
           u.login, u.email, u.idioma_preferido, c.aberto_em, c.primeira_resposta_em, c.resolvido_em,
           c.fechado_em, c.atualizado_em
    FROM plat.chamado c
    JOIN plat.tenant t ON t.id = c.tenant_id
    JOIN plat.usuario u ON u.id = c.aberto_por
    WHERE c.id = p_id;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_comentarios(p_sessao_hash text, p_id uuid)
RETURNS TABLE (s_id uuid, s_autor text, s_origem text, s_texto text, s_criado_em timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT k.id, u.login, k.origem, k.texto, k.criado_em
    FROM plat.chamado_comentario k
    JOIN plat.usuario u ON u.id = k.autor_id
    WHERE k.chamado_id = p_id
    ORDER BY k.criado_em;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_anexos(p_sessao_hash text, p_id uuid)
RETURNS TABLE (s_id uuid, s_nome text, s_tipo text, s_bytes int, s_sha256 text, s_criado_em timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  -- sem a coluna chave de propósito: a chave do objeto não sai do banco (o download vai por rota que a lê
  -- de novo, função a função — ver chamado_operador_anexo_chave)
  RETURN QUERY
    SELECT a.id, a.nome, a.tipo, a.bytes, a.sha256, a.criado_em
    FROM plat.chamado_anexo a
    WHERE a.chamado_id = p_id
    ORDER BY a.criado_em;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_anexo_chave(p_sessao_hash text, p_anexo_id uuid)
RETURNS TABLE (s_chave text, s_nome text, s_tipo text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v uuid;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT a.id INTO v FROM plat.chamado_anexo a WHERE a.id = p_anexo_id;
  IF v IS NULL THEN RAISE EXCEPTION 'anexo_inexistente'; END IF;
  RETURN QUERY SELECT a.chave, a.nome, a.tipo FROM plat.chamado_anexo a WHERE a.id = p_anexo_id;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_responder(p_sessao_hash text, p_id uuid, p_texto text,
                                                           p_operador_id int)
RETURNS TABLE (s_tenant_id int, s_numero int, s_titulo text, s_estado text, s_primeira_resposta_em timestamptz,
               s_aberto_por_id int, s_aberto_por_email text, s_aberto_por_idioma text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE c plat.chamado;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT * INTO c FROM plat.chamado WHERE id = p_id;
  IF c.id IS NULL THEN RAISE EXCEPTION 'chamado_inexistente'; END IF;
  IF c.estado = 'fechado' THEN RAISE EXCEPTION 'chamado_fechado'; END IF;
  INSERT INTO plat.chamado_comentario(tenant_id, chamado_id, autor_id, origem, texto)
    VALUES (c.tenant_id, c.id, p_operador_id, 'operador', p_texto);
  UPDATE plat.chamado SET
    primeira_resposta_em = coalesce(primeira_resposta_em, now()),
    -- responder a um chamado ainda sem triagem é assumi-lo: aberto -> em_analise; nos demais estados o
    -- estado só muda pela rota própria (transições validadas na aplicação)
    estado = CASE WHEN estado = 'aberto' THEN 'em_analise' ELSE estado END,
    atualizado_em = now()
  WHERE id = c.id RETURNING * INTO c;
  RETURN QUERY SELECT c.tenant_id, c.numero, c.titulo, c.estado, c.primeira_resposta_em,
                      c.aberto_por, u.email, u.idioma_preferido
               FROM plat.usuario u WHERE u.id = c.aberto_por;
END $$;

CREATE OR REPLACE FUNCTION plat.chamado_operador_estado(p_sessao_hash text, p_id uuid, p_estado text,
                                                        p_operador_id int)
RETURNS TABLE (s_tenant_id int, s_numero int, s_titulo text, s_estado text, s_primeira_resposta_em timestamptz,
               s_aberto_por_id int, s_aberto_por_email text, s_aberto_por_idioma text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE c plat.chamado;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT * INTO c FROM plat.chamado WHERE id = p_id;
  IF c.id IS NULL THEN RAISE EXCEPTION 'chamado_inexistente'; END IF;
  IF c.estado = 'fechado' THEN RAISE EXCEPTION 'chamado_fechado'; END IF;
  UPDATE plat.chamado SET
    estado = p_estado,
    primeira_resposta_em = coalesce(primeira_resposta_em, now()),
    resolvido_em = CASE WHEN p_estado = 'resolvido' THEN now() ELSE resolvido_em END,
    atualizado_em = now()
  WHERE id = c.id RETURNING * INTO c;
  RETURN QUERY SELECT c.tenant_id, c.numero, c.titulo, c.estado, c.primeira_resposta_em,
                      c.aberto_por, u.email, u.idioma_preferido
               FROM plat.usuario u WHERE u.id = c.aberto_por;
END $$;

-- As funções do operador são as únicas portas de entrada do painel: o GRANT de EXECUTE segue o padrão da 003
-- (todas as funções do schema para plat_app); a RLS das tabelas continua valendo para o resto.

-- ---------------------------------------------------------------- eventos de auditoria
-- plat.evento_tipo tem FK de plat.evento: todo tipo novo precisa estar aqui antes do primeiro uso.
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('chamado/abrir',    'chamado de suporte aberto pelo cliente'),
  ('chamado/comentar', 'comentário de cliente em chamado'),
  ('chamado/anexar',   'anexo de arquivo em chamado'),
  ('chamado/fechar',   'chamado fechado pelo cliente'),
  ('chamado/responder','resposta do operador ao chamado'),
  ('chamado/estado',   'mudança de estado do chamado pelo operador')
ON CONFLICT (nome) DO NOTHING;
