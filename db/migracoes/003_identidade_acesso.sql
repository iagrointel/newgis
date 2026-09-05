-- 003_identidade_acesso: privilégios e tetos por perfil, papéis personalizados, colunas novas de usuario,
-- histórico de senha, grupos, eventos e log_acesso particionados por mês, inquilino técnico `plataforma`,
-- funções SECURITY DEFINER reescritas com checagem de inquilino, REVOKE EXECUTE ... FROM PUBLIC em todas
-- (ADR 0002 seção 12). Idempotente. Sem BEGIN/COMMIT: o aplicador abre a transação. Aplicada como postgres.

-- ---------------------------------------------------------------- 12.1 privilégios e tetos (vocabulário fechado)
CREATE TABLE IF NOT EXISTS plat.privilegio (
  nome           text PRIMARY KEY CHECK (nome ~ '^[a-z]+\.[a-z_]+$'),
  grupo          text NOT NULL,
  descricao      text NOT NULL,
  administrativo boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS plat.perfil_privilegio (
  perfil     text NOT NULL CHECK (perfil IN ('admin','editor','visualizador','campo')),
  privilegio text NOT NULL REFERENCES plat.privilegio(nome),
  PRIMARY KEY (perfil, privilegio)
);
-- 46 privilégios (espelho de app/auth/privilegios.py; gerado uma vez, o teste compara os dois)
INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('membros.ver', 'membros', 'ver nome, login, perfil e último acesso dos membros do inquilino', false),
  ('membros.ver_tudo', 'membros', 'ver e-mail, IP, sessões, tokens e 2FA de qualquer membro', true),
  ('membros.gerir', 'membros', 'criar, editar nome/e-mail, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear', true),
  ('membros.papel', 'membros', 'mudar perfil e papel (para/de admin só quem é admin)', true),
  ('membros.apagar', 'membros', 'apagar membro (só sem conteúdo e sem grupo)', true),
  ('papeis.gerir', 'papeis', 'criar, editar, apagar papel personalizado', true),
  ('grupos.ver_inquilino', 'grupos', 'ver grupos com visibilidade inquilino', false),
  ('grupos.entrar', 'grupos', 'pedir entrada ou entrar em grupo de entrada livre', false),
  ('grupos.criar', 'grupos', 'criar, editar e apagar os próprios grupos', false),
  ('grupos.atualizacao_compartilhada', 'grupos', 'criar grupo com atualização compartilhada', false),
  ('grupos.administrativo', 'grupos', 'criar grupo administrativo (membro não sai)', true),
  ('grupos.gerir_todos', 'grupos', 'editar, apagar, transferir dono e gerir membros de qualquer grupo', true),
  ('conteudo.ver_inquilino', 'conteudo', 'ver itens compartilhados com o inquilino', false),
  ('conteudo.criar', 'conteudo', 'criar, editar e apagar os próprios itens (mapa, app, pasta)', false),
  ('conteudo.publicar_camada', 'conteudo', 'publicar camada vetorial hospedada', false),
  ('conteudo.publicar_tiles', 'conteudo', 'publicar tiles vetoriais', false),
  ('conteudo.publicar_raster', 'conteudo', 'publicar imagem/raster', false),
  ('conteudo.registrar_fonte', 'conteudo', 'registrar fonte de dado externa', false),
  ('conteudo.categorias', 'conteudo', 'gerir categorias do inquilino', true),
  ('conteudo.ver_tudo', 'conteudo', 'ver qualquer item do inquilino, inclusive privado', true),
  ('conteudo.editar_tudo', 'conteudo', 'editar metadado e dado de qualquer item', true),
  ('conteudo.apagar_tudo', 'conteudo', 'apagar/restaurar qualquer item', true),
  ('conteudo.transferir', 'conteudo', 'mudar dono de item', true),
  ('compartilhar.grupo', 'compartilhar', 'compartilhar item com grupo em que pode contribuir', false),
  ('compartilhar.inquilino', 'compartilhar', 'compartilhar item com todo o inquilino', false),
  ('compartilhar.link', 'compartilhar', 'criar link por token', false),
  ('compartilhar.publico', 'compartilhar', 'tornar item público (só com config.compartilhar_publico)', true),
  ('feicoes.editar', 'feicoes', 'editar feições de camada compartilhada com edição habilitada', false),
  ('feicoes.editar_total', 'feicoes', 'editar qualquer camada, mesmo sem edição habilitada', true),
  ('campo.coletar', 'campo', 'usar formulários e a PWA de campo', false),
  ('campo.localizacao', 'campo', 'compartilhar localização/trilhas', false),
  ('analise.geocodificar', 'analise', 'geocodificar e buscar lugar', false),
  ('analise.rotas', 'analise', 'rotas e isócronas', false),
  ('analise.executar', 'analise', 'geoprocessamento sobre dado próprio', false),
  ('analise.amc', 'analise', 'criar e executar modelo multicritério', false),
  ('analise.raster', 'analise', 'análise de imagem', false),
  ('rede.tracar', 'rede', 'traçado e subrede', false),
  ('rede.editar', 'rede', 'editar rede de utilidades', false),
  ('jobs.executar', 'jobs', 'ver e cancelar os próprios jobs', false),
  ('jobs.gerir_todos', 'jobs', 'ver e cancelar jobs de qualquer membro', true),
  ('tokens.gerar', 'tokens', 'criar e revogar os próprios tokens de serviço', false),
  ('tokens.gerir_todos', 'tokens', 'ver e revogar tokens de qualquer membro', true),
  ('org.configurar', 'org', 'editar tenant.config, política de senha, exigir 2FA, domínios de e-mail', true),
  ('org.log_ver', 'org', 'ler log_acesso e evento do inquilino, exportar CSV', true),
  ('org.exportar', 'org', 'exportar o inquilino, relatórios', true),
  ('org.integracoes', 'org', 'SSO, SMTP, webhooks, CORS', true)
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao, administrativo = EXCLUDED.administrativo;
-- tetos por perfil (V, C, E, A)
INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES
  ('visualizador', 'membros.ver'),
  ('visualizador', 'grupos.ver_inquilino'),
  ('visualizador', 'grupos.entrar'),
  ('visualizador', 'conteudo.ver_inquilino'),
  ('visualizador', 'analise.geocodificar'),
  ('visualizador', 'analise.rotas'),
  ('visualizador', 'tokens.gerar'),
  ('campo', 'membros.ver'),
  ('campo', 'grupos.ver_inquilino'),
  ('campo', 'grupos.entrar'),
  ('campo', 'conteudo.ver_inquilino'),
  ('campo', 'feicoes.editar'),
  ('campo', 'campo.coletar'),
  ('campo', 'campo.localizacao'),
  ('campo', 'analise.geocodificar'),
  ('campo', 'analise.rotas'),
  ('campo', 'jobs.executar'),
  ('campo', 'tokens.gerar'),
  ('editor', 'membros.ver'),
  ('editor', 'grupos.ver_inquilino'),
  ('editor', 'grupos.entrar'),
  ('editor', 'grupos.criar'),
  ('editor', 'grupos.atualizacao_compartilhada'),
  ('editor', 'conteudo.ver_inquilino'),
  ('editor', 'conteudo.criar'),
  ('editor', 'conteudo.publicar_camada'),
  ('editor', 'conteudo.publicar_tiles'),
  ('editor', 'conteudo.publicar_raster'),
  ('editor', 'conteudo.registrar_fonte'),
  ('editor', 'compartilhar.grupo'),
  ('editor', 'compartilhar.inquilino'),
  ('editor', 'compartilhar.link'),
  ('editor', 'feicoes.editar'),
  ('editor', 'campo.coletar'),
  ('editor', 'campo.localizacao'),
  ('editor', 'analise.geocodificar'),
  ('editor', 'analise.rotas'),
  ('editor', 'analise.executar'),
  ('editor', 'analise.amc'),
  ('editor', 'analise.raster'),
  ('editor', 'rede.tracar'),
  ('editor', 'rede.editar'),
  ('editor', 'jobs.executar'),
  ('editor', 'tokens.gerar'),
  ('admin', 'membros.ver'),
  ('admin', 'membros.ver_tudo'),
  ('admin', 'membros.gerir'),
  ('admin', 'membros.papel'),
  ('admin', 'membros.apagar'),
  ('admin', 'papeis.gerir'),
  ('admin', 'grupos.ver_inquilino'),
  ('admin', 'grupos.entrar'),
  ('admin', 'grupos.criar'),
  ('admin', 'grupos.atualizacao_compartilhada'),
  ('admin', 'grupos.administrativo'),
  ('admin', 'grupos.gerir_todos'),
  ('admin', 'conteudo.ver_inquilino'),
  ('admin', 'conteudo.criar'),
  ('admin', 'conteudo.publicar_camada'),
  ('admin', 'conteudo.publicar_tiles'),
  ('admin', 'conteudo.publicar_raster'),
  ('admin', 'conteudo.registrar_fonte'),
  ('admin', 'conteudo.categorias'),
  ('admin', 'conteudo.ver_tudo'),
  ('admin', 'conteudo.editar_tudo'),
  ('admin', 'conteudo.apagar_tudo'),
  ('admin', 'conteudo.transferir'),
  ('admin', 'compartilhar.grupo'),
  ('admin', 'compartilhar.inquilino'),
  ('admin', 'compartilhar.link'),
  ('admin', 'compartilhar.publico'),
  ('admin', 'feicoes.editar'),
  ('admin', 'feicoes.editar_total'),
  ('admin', 'campo.coletar'),
  ('admin', 'campo.localizacao'),
  ('admin', 'analise.geocodificar'),
  ('admin', 'analise.rotas'),
  ('admin', 'analise.executar'),
  ('admin', 'analise.amc'),
  ('admin', 'analise.raster'),
  ('admin', 'rede.tracar'),
  ('admin', 'rede.editar'),
  ('admin', 'jobs.executar'),
  ('admin', 'jobs.gerir_todos'),
  ('admin', 'tokens.gerar'),
  ('admin', 'tokens.gerir_todos'),
  ('admin', 'org.configurar'),
  ('admin', 'org.log_ver'),
  ('admin', 'org.exportar'),
  ('admin', 'org.integracoes')
ON CONFLICT DO NOTHING;
REVOKE INSERT, UPDATE, DELETE ON plat.privilegio, plat.perfil_privilegio FROM plat_app;

-- ---------------------------------------------------------------- 12.2 papéis personalizados (por inquilino, RLS)
CREATE TABLE IF NOT EXISTS plat.papel_personalizado (
  id            serial PRIMARY KEY,
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128),
  descricao     text CHECK (descricao IS NULL OR length(descricao) <= 250),
  perfil_minimo text NOT NULL CHECK (perfil_minimo IN ('admin','editor','visualizador','campo')),
  criado_por    int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_papel_tenant_nome ON plat.papel_personalizado (tenant_id, lower(nome));
CREATE TABLE IF NOT EXISTS plat.papel_privilegio (
  papel_id   int NOT NULL REFERENCES plat.papel_personalizado(id) ON DELETE CASCADE,
  privilegio text NOT NULL REFERENCES plat.privilegio(nome),
  PRIMARY KEY (papel_id, privilegio)
);
ALTER TABLE plat.papel_personalizado ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.papel_privilegio    ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_papel_personalizado ON plat.papel_personalizado;
CREATE POLICY p_papel_personalizado ON plat.papel_personalizado FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_papel_privilegio ON plat.papel_privilegio;
CREATE POLICY p_papel_privilegio ON plat.papel_privilegio FOR ALL TO plat_app
  USING (EXISTS (SELECT 1 FROM plat.papel_personalizado p WHERE p.id = papel_id))
  WITH CHECK (EXISTS (SELECT 1 FROM plat.papel_personalizado p WHERE p.id = papel_id));

-- ---------------------------------------------------------------- 12.3 usuario: colunas novas
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS papel_id int REFERENCES plat.papel_personalizado(id);
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS origem text NOT NULL DEFAULT 'local';
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS sujeito_externo text;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS trocar_senha boolean NOT NULL DEFAULT false;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS falhas_desde timestamptz;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS totp_ultimo_passo bigint;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS codigos_recuperacao text[];
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS desafio_2fa_hash text;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS desafio_2fa_ate timestamptz;
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS ultimo_ip text;
ALTER TABLE plat.usuario ALTER COLUMN senha_hash DROP NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_origem') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_origem CHECK (origem IN ('local','oidc','saml','ldap'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_senha_local') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_senha_local CHECK (origem <> 'local' OR senha_hash IS NOT NULL);
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuario_sujeito_externo ON plat.usuario (tenant_id, origem, sujeito_externo)
  WHERE sujeito_externo IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_usuario_desafio ON plat.usuario (desafio_2fa_hash) WHERE desafio_2fa_hash IS NOT NULL;

-- token_servico: rotação registra o sucessor (ADR 0002 seção 8.1; coluna nova, nada da 002 muda)
ALTER TABLE plat.token_servico ADD COLUMN IF NOT EXISTS renovado_por int REFERENCES plat.token_servico(id);

-- ---------------------------------------------------------------- 12.10 privilégios efetivos e plat.tem (depois de 12.3 e antes de 12.5: lê usuario.papel_id; a política de grupo usa plat.tem)
CREATE OR REPLACE FUNCTION plat.privilegios_de(p_usuario int) RETURNS text[]
LANGUAGE sql STABLE SET search_path = plat, public AS $$
  SELECT coalesce(array_agg(pp.privilegio ORDER BY pp.privilegio), '{}'::text[])
  FROM plat.usuario u
  JOIN plat.perfil_privilegio pp ON pp.perfil = u.perfil
  WHERE u.id = p_usuario
    AND (u.papel_id IS NULL
         OR EXISTS (SELECT 1 FROM plat.papel_privilegio x WHERE x.papel_id = u.papel_id AND x.privilegio = pp.privilegio))
$$;
CREATE OR REPLACE FUNCTION plat.tem(p_privilegio text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = plat, public AS $$
  SELECT p_privilegio = ANY (plat.privilegios_de(plat.usuario_atual()))
$$;

-- ---------------------------------------------------------------- 12.4 histórico de senha (RLS via usuario)
CREATE TABLE IF NOT EXISTS plat.senha_historico (
  id         bigserial PRIMARY KEY,
  usuario_id int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  senha_hash text NOT NULL,
  criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_senha_historico_usuario ON plat.senha_historico (usuario_id, criado_em DESC);
ALTER TABLE plat.senha_historico ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_senha_historico ON plat.senha_historico;
CREATE POLICY p_senha_historico ON plat.senha_historico FOR ALL TO plat_app
  USING (EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = usuario_id))
  WITH CHECK (EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = usuario_id));

-- ---------------------------------------------------------------- 12.5 grupos (UUID) e membros
CREATE TABLE IF NOT EXISTS plat.grupo (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 int NOT NULL REFERENCES plat.tenant(id),
  nome                      text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128),
  resumo                    text CHECK (resumo IS NULL OR length(resumo) <= 2048),
  tags                      text[] NOT NULL DEFAULT '{}' CHECK (cardinality(tags) <= 50),
  visibilidade              text NOT NULL DEFAULT 'membros' CHECK (visibilidade IN ('membros','inquilino')),
  entrada                   text NOT NULL DEFAULT 'convite' CHECK (entrada IN ('convite','pedido','livre')),
  contribuicao              text NOT NULL DEFAULT 'todos' CHECK (contribuicao IN ('todos','dono_gerentes')),
  atualizacao_compartilhada boolean NOT NULL DEFAULT false,
  administrativo            boolean NOT NULL DEFAULT false,
  protegido                 boolean NOT NULL DEFAULT false,
  dono_id                   int NOT NULL REFERENCES plat.usuario(id),
  criado_em                 timestamptz NOT NULL DEFAULT now(),
  CHECK (NOT atualizacao_compartilhada OR entrada IN ('convite','pedido'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_grupo_tenant_nome ON plat.grupo (tenant_id, lower(nome));
CREATE INDEX IF NOT EXISTS ix_grupo_dono ON plat.grupo (dono_id);
-- tenant_id denormalizado em grupo_membro: a política de grupo consulta grupo_membro e a de grupo_membro NÃO pode
-- consultar grupo de volta (recursão infinita de política); a coerência é garantida por gatilho abaixo
CREATE TABLE IF NOT EXISTS plat.grupo_membro (
  grupo_id      uuid NOT NULL REFERENCES plat.grupo(id) ON DELETE CASCADE,
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  usuario_id    int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  papel         text NOT NULL DEFAULT 'membro' CHECK (papel IN ('dono','gerente','membro')),
  estado        text NOT NULL DEFAULT 'ativo' CHECK (estado IN ('ativo','convidado','pedido')),
  convidado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (grupo_id, usuario_id)
);
CREATE INDEX IF NOT EXISTS ix_grupo_membro_usuario ON plat.grupo_membro (usuario_id);
ALTER TABLE plat.grupo        ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.grupo_membro ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_grupo ON plat.grupo;
DROP POLICY IF EXISTS p_grupo_ler ON plat.grupo;
CREATE POLICY p_grupo_ler ON plat.grupo FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (
           (visibilidade = 'inquilino' AND plat.tem('grupos.ver_inquilino'))
           OR plat.tem('grupos.gerir_todos')
           OR EXISTS (SELECT 1 FROM plat.grupo_membro m WHERE m.grupo_id = id AND m.usuario_id = plat.usuario_atual())));
DROP POLICY IF EXISTS p_grupo_inserir ON plat.grupo;
CREATE POLICY p_grupo_inserir ON plat.grupo FOR INSERT TO plat_app WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_grupo_alterar ON plat.grupo;
CREATE POLICY p_grupo_alterar ON plat.grupo FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_grupo_apagar ON plat.grupo;
CREATE POLICY p_grupo_apagar ON plat.grupo FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_grupo_membro ON plat.grupo_membro;
CREATE POLICY p_grupo_membro ON plat.grupo_membro FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- 12.6 gatilhos
-- último admin ativo do inquilino não se desabilita, não se rebaixa, não se apaga
CREATE OR REPLACE FUNCTION plat.tg_usuario_ultimo_admin() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF OLD.perfil = 'admin' AND OLD.ativo
     AND (TG_OP = 'DELETE' OR NEW.perfil <> 'admin' OR NOT NEW.ativo) THEN
    IF NOT EXISTS (SELECT 1 FROM plat.usuario u
                   WHERE u.tenant_id = OLD.tenant_id AND u.id <> OLD.id AND u.perfil = 'admin' AND u.ativo) THEN
      RAISE EXCEPTION 'ultimo_admin' USING HINT = 'nomeie outro administrador antes';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS usuario_ultimo_admin ON plat.usuario;
CREATE TRIGGER usuario_ultimo_admin BEFORE UPDATE OR DELETE ON plat.usuario
  FOR EACH ROW EXECUTE FUNCTION plat.tg_usuario_ultimo_admin();

-- superadmin só no inquilino técnico `plataforma` (dado existente é corrigido ANTES de o gatilho valer)
INSERT INTO plat.tenant(slug, nome, config)
VALUES ('plataforma', 'Operação da plataforma', '{"auth": {"exigir_2fa": true}}'::jsonb)
ON CONFLICT (slug) DO NOTHING;
UPDATE plat.tenant SET ativo = true,
  config = jsonb_set(CASE WHEN config ? 'auth' THEN config ELSE config || '{"auth": {}}'::jsonb END,
                     '{auth,exigir_2fa}', 'true'::jsonb, true)
WHERE slug = 'plataforma' AND (NOT ativo OR coalesce(config #>> '{auth,exigir_2fa}', '') <> 'true');
UPDATE plat.usuario SET superadmin = false
WHERE superadmin AND tenant_id <> (SELECT id FROM plat.tenant WHERE slug = 'plataforma');
CREATE OR REPLACE FUNCTION plat.tg_usuario_superadmin() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF NEW.superadmin AND NOT EXISTS (SELECT 1 FROM plat.tenant t WHERE t.id = NEW.tenant_id AND t.slug = 'plataforma') THEN
    RAISE EXCEPTION 'superadmin_so_plataforma';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS usuario_superadmin_so_plataforma ON plat.usuario;
CREATE TRIGGER usuario_superadmin_so_plataforma BEFORE INSERT OR UPDATE OF superadmin, tenant_id ON plat.usuario
  FOR EACH ROW EXECUTE FUNCTION plat.tg_usuario_superadmin();

-- grupo.dono_id e a linha `dono` de grupo_membro sempre em acordo; dono do mesmo inquilino
CREATE OR REPLACE FUNCTION plat.tg_grupo_dono_coerente() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.dono_id AND u.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'dono_de_outro_inquilino';
  END IF;
  UPDATE plat.grupo_membro SET papel = 'gerente'
  WHERE grupo_id = NEW.id AND papel = 'dono' AND usuario_id <> NEW.dono_id;
  INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado)
  VALUES (NEW.id, NEW.tenant_id, NEW.dono_id, 'dono', 'ativo')
  ON CONFLICT (grupo_id, usuario_id) DO UPDATE SET papel = 'dono', estado = 'ativo';
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS grupo_dono_coerente ON plat.grupo;
CREATE TRIGGER grupo_dono_coerente AFTER INSERT OR UPDATE OF dono_id ON plat.grupo
  FOR EACH ROW EXECUTE FUNCTION plat.tg_grupo_dono_coerente();

-- grupo_membro: membro do mesmo inquilino e do inquilino do grupo; a linha do dono não sai nem se rebaixa por aqui
CREATE OR REPLACE FUNCTION plat.tg_grupo_membro_coerente() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.usuario_id AND u.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'usuario_de_outro_inquilino';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM plat.grupo g WHERE g.id = NEW.grupo_id AND g.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'grupo_de_outro_inquilino';
    END IF;
  END IF;
  IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.papel = 'dono'
     AND (TG_OP = 'DELETE' OR NEW.papel <> 'dono' OR NEW.estado <> 'ativo')
     AND EXISTS (SELECT 1 FROM plat.grupo g WHERE g.id = OLD.grupo_id AND g.dono_id = OLD.usuario_id) THEN
    RAISE EXCEPTION 'dono_nao_sai';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS grupo_membro_coerente ON plat.grupo_membro;
CREATE TRIGGER grupo_membro_coerente BEFORE INSERT OR UPDATE OR DELETE ON plat.grupo_membro
  FOR EACH ROW EXECUTE FUNCTION plat.tg_grupo_membro_coerente();

-- ---------------------------------------------------------------- 12.7 eventos de domínio (append-only, particionado)
CREATE TABLE IF NOT EXISTS plat.evento_tipo (nome text PRIMARY KEY, descricao text NOT NULL);
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('usuarios/entrar', 'login com sucesso (propriedades.fator: senha|totp|recuperacao)'),
  ('usuarios/sair', 'logout'),
  ('usuarios/falha_login', 'falha de login que bloqueou o usuário'),
  ('usuarios/criar', 'usuário criado pelo admin'),
  ('usuarios/atualizar', 'nome, e-mail ou ativo alterados'),
  ('usuarios/desabilitar', 'usuário desabilitado'),
  ('usuarios/reabilitar', 'usuário reabilitado'),
  ('usuarios/apagar', 'usuário apagado'),
  ('usuarios/papel', 'perfil ou papel alterados (antes/depois em propriedades)'),
  ('usuarios/redefinir_senha', 'senha temporária gerada pelo admin'),
  ('usuarios/trocar_senha', 'senha trocada pelo próprio usuário'),
  ('usuarios/2fa_ligar', 'segundo fator ligado'),
  ('usuarios/2fa_desligar', 'segundo fator desligado (ator ≠ alvo quando pelo admin)'),
  ('usuarios/2fa_codigos', 'códigos de recuperação regenerados'),
  ('usuarios/desbloquear', 'bloqueio removido pelo admin'),
  ('papeis/criar', 'papel personalizado criado'),
  ('papeis/atualizar', 'papel personalizado alterado'),
  ('papeis/apagar', 'papel personalizado apagado'),
  ('grupos/criar', 'grupo criado'),
  ('grupos/atualizar', 'grupo alterado'),
  ('grupos/apagar', 'grupo apagado'),
  ('grupos/transferir', 'dono do grupo transferido'),
  ('grupos/convidar', 'usuário convidado para grupo (alvo = usuário)'),
  ('grupos/pedir', 'pedido de entrada em grupo'),
  ('grupos/aprovar', 'pedido aprovado'),
  ('grupos/entrar', 'entrada em grupo (aceite de convite ou entrada livre)'),
  ('grupos/recusar', 'convite recusado'),
  ('grupos/sair', 'saída de grupo'),
  ('grupos/remover', 'membro removido'),
  ('grupos/papel', 'papel de membro alterado'),
  ('tokens/criar', 'token de serviço criado'),
  ('tokens/renovar', 'token de serviço rotacionado'),
  ('tokens/revogar', 'token de serviço revogado'),
  ('sessoes/revogar', 'sessão encerrada pela tela'),
  ('inquilinos/criar', 'inquilino criado pelo superadmin'),
  ('inquilinos/suspender', 'inquilino suspenso'),
  ('inquilinos/reativar', 'inquilino reativado'),
  ('inquilinos/leitura_superadmin', 'superadmin leu dado do inquilino (X-Plat-Inquilino)')
ON CONFLICT (nome) DO NOTHING;
REVOKE INSERT, UPDATE, DELETE ON plat.evento_tipo FROM plat_app;

CREATE TABLE IF NOT EXISTS plat.evento (
  id           bigserial,
  em           timestamptz NOT NULL DEFAULT now(),
  tenant_id    int NOT NULL,
  ator_id      int,
  tipo         text NOT NULL REFERENCES plat.evento_tipo(nome),
  alvo_tipo    text,
  alvo_id      text,
  propriedades jsonb NOT NULL DEFAULT '{}'::jsonb,
  ip           text,
  req_id       text,
  PRIMARY KEY (id, em)
) PARTITION BY RANGE (em);
CREATE INDEX IF NOT EXISTS ix_evento_tenant_em ON plat.evento (tenant_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_evento_tenant_tipo ON plat.evento (tenant_id, tipo, em DESC);
ALTER TABLE plat.evento ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_evento ON plat.evento;
CREATE POLICY p_evento ON plat.evento FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
REVOKE INSERT, UPDATE, DELETE ON plat.evento FROM plat_app;

CREATE OR REPLACE FUNCTION plat.evento_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
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

CREATE OR REPLACE FUNCTION plat.evento_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
BEGIN
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.evento'::regclass LOOP
    IF to_date(substring(r.relname FROM 'y(\d{4})m(\d{2})$'), 'YYYY') IS NOT NULL
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.evento_registrar(p_tipo text, p_alvo_tipo text, p_alvo_id text, p_propriedades jsonb,
  p_ip text, p_req_id text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE novo bigint;
BEGIN
  IF plat.tenant_atual() IS NULL THEN
    RAISE EXCEPTION 'evento_sem_contexto' USING HINT = 'evento_registrar exige o contexto do inquilino';
  END IF;
  BEGIN
    INSERT INTO plat.evento(tenant_id, ator_id, tipo, alvo_tipo, alvo_id, propriedades, ip, req_id)
    VALUES (plat.tenant_atual(), plat.usuario_atual(), p_tipo, p_alvo_tipo, p_alvo_id,
            coalesce(p_propriedades, '{}'::jsonb), p_ip, p_req_id) RETURNING id INTO novo;
  EXCEPTION WHEN check_violation THEN
    PERFORM plat.evento_particao_garantir(now()::date);
    INSERT INTO plat.evento(tenant_id, ator_id, tipo, alvo_tipo, alvo_id, propriedades, ip, req_id)
    VALUES (plat.tenant_atual(), plat.usuario_atual(), p_tipo, p_alvo_tipo, p_alvo_id,
            coalesce(p_propriedades, '{}'::jsonb), p_ip, p_req_id) RETURNING id INTO novo;
  END;
  RETURN novo;
END $$;

-- ---------------------------------------------------------------- 12.8 log_acesso particionado por mês
DO $$
DECLARE k char; n bigint;
BEGIN
  SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('plat.log_acesso');
  IF k = 'r' THEN
    EXECUTE 'SELECT count(*) FROM plat.log_acesso' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'plat.log_acesso tem % linhas: copie antes de particionar (ADR 0002 seção 12.8)', n;
    END IF;
    DROP TABLE plat.log_acesso;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS plat.log_acesso (
  id           bigserial,
  em           timestamptz NOT NULL DEFAULT now(),
  tenant_id    int,
  usuario_id   int,
  token_id     int,
  ip           text,
  metodo       text NOT NULL,
  rota         text NOT NULL,
  status       int NOT NULL,
  bytes        bigint NOT NULL DEFAULT 0,
  tempo_ms     int NOT NULL,
  agente       text,
  resultado    text,
  PRIMARY KEY (id, em)
) PARTITION BY RANGE (em);
CREATE INDEX IF NOT EXISTS ix_log_acesso_tenant_em ON plat.log_acesso (tenant_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_log_acesso_token_em  ON plat.log_acesso (token_id, em DESC) WHERE token_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_log_acesso_usuario_em ON plat.log_acesso (tenant_id, usuario_id, em DESC);
ALTER TABLE plat.log_acesso ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_log_acesso ON plat.log_acesso;
CREATE POLICY p_log_acesso ON plat.log_acesso FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
REVOKE INSERT, UPDATE, DELETE ON plat.log_acesso FROM plat_app;

CREATE OR REPLACE FUNCTION plat.log_particao_garantir(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE ini date := date_trunc('month', p_mes)::date; fim date; nome text;
BEGIN
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

CREATE OR REPLACE FUNCTION plat.log_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
BEGIN
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.log_acesso'::regclass LOOP
    IF (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

-- mês corrente e três à frente, para log e evento (o install.sh repete a chamada a cada execução; L0-05-d agenda)
SELECT plat.log_particao_garantir((date_trunc('month', now()) + make_interval(months => m))::date),
       plat.evento_particao_garantir((date_trunc('month', now()) + make_interval(months => m))::date)
FROM generate_series(0, 3) AS m;

-- ---------------------------------------------------------------- funções SECURITY DEFINER (assinaturas novas: DROP das antigas)
DROP FUNCTION IF EXISTS plat.auth_login(text, text);
DROP FUNCTION IF EXISTS plat.auth_falha(int, int, int);
DROP FUNCTION IF EXISTS plat.auth_ok(int);
DROP FUNCTION IF EXISTS plat.auth_sessao(text);
DROP FUNCTION IF EXISTS plat.auth_token(text, text);
DROP FUNCTION IF EXISTS plat.auth_sessao_criar(int, int, text, text);
DROP FUNCTION IF EXISTS plat.log_registrar(int, int, int, text, text, text, int, bigint, int, text, text);
DROP FUNCTION IF EXISTS plat.tenant_criar(text, text, jsonb, text, text, text);

CREATE OR REPLACE FUNCTION plat.contexto_confere(p_usuario int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  SELECT tenant_id INTO tid FROM plat.usuario WHERE id = p_usuario;
  IF tid IS NULL THEN RAISE EXCEPTION 'usuario_inexistente'; END IF;
  IF plat.tenant_atual() IS DISTINCT FROM tid THEN
    RAISE EXCEPTION 'contexto_de_outro_inquilino' USING HINT = 'a função exige o contexto do inquilino do usuário';
  END IF;
  RETURN tid;
END $$;

-- pré-contexto: resolve o inquilino pelo slug; devolve o que o login precisa (nunca totp_secret)
CREATE OR REPLACE FUNCTION plat.auth_login(p_tenant text, p_login text)
RETURNS TABLE (usuario_id int, tenant_id int, senha_hash text, perfil text, nome text, tenant_nome text,
               totp_ativo boolean, bloqueado_ate timestamptz, falhas_login int, superadmin boolean, origem text,
               trocar_senha boolean, ativo boolean, ativo_tenant boolean, config jsonb, senha_alterada_em timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT u.id, u.tenant_id, u.senha_hash, u.perfil, u.nome, t.nome, u.totp_ativo, u.bloqueado_ate, u.falhas_login,
         u.superadmin, u.origem, u.trocar_senha, u.ativo, t.ativo, t.config, u.senha_alterada_em
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE t.slug = p_tenant AND u.login = lower(p_login)
$$;

-- pré-contexto: o que a tela de login precisa saber do inquilino antes de qualquer credencial (slug, nome, ativo)
CREATE OR REPLACE FUNCTION plat.tenant_publico(p_slug text)
RETURNS TABLE (id int, slug text, nome text, ativo boolean)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id, t.slug, t.nome, t.ativo FROM plat.tenant t WHERE t.slug = p_slug
$$;

-- contexto obrigatório: janela de 15 min, bloqueio ao atingir p_max; devolve bloqueado_ate
CREATE OR REPLACE FUNCTION plat.auth_falha(p_usuario int, p_max int, p_min int, p_janela_min int) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE u record; falhas int; desde timestamptz; ate timestamptz;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  SELECT falhas_login, falhas_desde INTO u FROM plat.usuario WHERE id = p_usuario;
  IF u.falhas_desde IS NULL OR u.falhas_desde < now() - make_interval(mins => p_janela_min) THEN
    falhas := 1; desde := now();
  ELSE
    falhas := u.falhas_login + 1; desde := u.falhas_desde;
  END IF;
  UPDATE plat.usuario SET falhas_login = falhas, falhas_desde = desde,
    bloqueado_ate = CASE WHEN falhas >= p_max THEN now() + make_interval(mins => p_min) ELSE bloqueado_ate END
  WHERE id = p_usuario RETURNING bloqueado_ate INTO ate;
  RETURN ate;
END $$;

CREATE OR REPLACE FUNCTION plat.auth_ok(p_usuario int, p_ip text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  UPDATE plat.usuario SET falhas_login = 0, falhas_desde = NULL, bloqueado_ate = NULL, ultimo_login = now(),
    ultimo_ip = p_ip WHERE id = p_usuario;
END $$;

CREATE OR REPLACE FUNCTION plat.auth_sessao_criar(p_usuario int, p_max_dias int, p_ip text, p_agente text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tok text; tid int;
BEGIN
  tid := plat.contexto_confere(p_usuario);
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
                 WHERE u.id = p_usuario AND u.ativo AND t.ativo) THEN
    RAISE EXCEPTION 'usuario_inativo_ou_inquilino_suspenso';
  END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO plat.sessao(token_hash, tenant_id, usuario_id, expira_em, ip, agente, ultimo_uso)
  VALUES (encode(sha256(convert_to(tok, 'UTF8')), 'hex'), tid, p_usuario,
          now() + make_interval(days => greatest(p_max_dias, 1)), p_ip, left(p_agente, 200), now());
  RETURN tok;
END $$;

-- pré-contexto (o hash é o segredo): valida absoluto + ocioso; ocioso vem de config.auth do inquilino quando
-- existe (cortado a 1–24 h), senão de p_ociosa_horas (a API passa o padrão, ou o valor de teste em dev)
CREATE OR REPLACE FUNCTION plat.auth_sessao(p_hash text, p_ociosa_horas numeric)
RETURNS TABLE (usuario_id int, tenant_id int, login text, perfil text, nome text, email text, tenant_slug text,
               tenant_nome text, superadmin boolean, config jsonb, privilegios text[], trocar_senha boolean,
               totp_ativo boolean, origem text, papel_id int, expira_em timestamptz, ultimo_uso timestamptz,
               criado_em timestamptz, ip text, ociosa_horas numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s record; ociosa numeric;
BEGIN
  SELECT x.token_hash, x.expira_em, x.ultimo_uso, x.criado_em, x.ip, u.ativo AS u_ativo, t.ativo AS t_ativo,
         t.config AS cfg
  INTO s
  FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
  WHERE x.token_hash = p_hash;
  IF NOT FOUND THEN RETURN; END IF;
  -- GREATEST/LEAST ignoram NULL no PostgreSQL: sem a chave no config, vale p_ociosa_horas (padrão da plataforma
  -- ou o valor de teste em dev); com a chave, corta para 1–24 h
  ociosa := CASE WHEN nullif(s.cfg #>> '{auth,sessao_ociosa_horas}', '') IS NULL THEN p_ociosa_horas
                 ELSE least(greatest((s.cfg #>> '{auth,sessao_ociosa_horas}')::numeric, 1), 24) END;
  IF NOT (s.expira_em > now() AND coalesce(s.ultimo_uso, s.criado_em) >= now() - make_interval(secs => ociosa * 3600)
          AND s.u_ativo AND s.t_ativo) THEN
    RETURN;
  END IF;
  UPDATE plat.sessao SET ultimo_uso = now() WHERE token_hash = p_hash;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, t.slug, t.nome, u.superadmin, t.config,
           plat.privilegios_de(u.id), u.trocar_senha, u.totp_ativo, u.origem, u.papel_id, x.expira_em, x.ultimo_uso,
           x.criado_em, x.ip, ociosa
    FROM plat.sessao x JOIN plat.usuario u ON u.id = x.usuario_id JOIN plat.tenant t ON t.id = x.tenant_id
    WHERE x.token_hash = p_hash;
END $$;

CREATE OR REPLACE FUNCTION plat.auth_sessao_encerrar(p_hash text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  DELETE FROM plat.sessao WHERE token_hash = p_hash
$$;

-- contexto obrigatório: apaga todas as sessões do usuário (menos p_exceto_hash) e o desafio de 2FA pendente
CREATE OR REPLACE FUNCTION plat.sessoes_encerrar_usuario(p_usuario int, p_exceto_hash text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  DELETE FROM plat.sessao WHERE usuario_id = p_usuario AND (p_exceto_hash IS NULL OR token_hash <> p_exceto_hash);
  GET DIAGNOSTICS n = ROW_COUNT;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL WHERE id = p_usuario;
  RETURN n;
END $$;

-- operação da plataforma (sem inquilino): sessões vencidas e desafios expirados
CREATE OR REPLACE FUNCTION plat.sessoes_expurgar() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.sessao WHERE expira_em < now() OR coalesce(ultimo_uso, criado_em) < now() - interval '24 hours';
  GET DIAGNOSTICS n = ROW_COUNT;
  UPDATE plat.usuario SET desafio_2fa_hash = NULL, desafio_2fa_ate = NULL
  WHERE desafio_2fa_ate IS NOT NULL AND desafio_2fa_ate < now();
  RETURN n;
END $$;

-- pré-contexto: devolve a linha mesmo revogada/expirada (a API nomeia o motivo); só escreve ultimo_uso quando válido
CREATE OR REPLACE FUNCTION plat.auth_token(p_hash text, p_ip text)
RETURNS TABLE (usuario_id int, tenant_id int, login text, perfil text, nome text, email text, escopos text[],
               restricao jsonb, token_id int, token_nome text, privilegios text[], trocar_senha boolean,
               expira_em timestamptz, revogado_em timestamptz, renovado_por int, superadmin boolean,
               totp_ativo boolean, origem text, tenant_slug text, tenant_nome text, config jsonb, papel_id int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  UPDATE plat.token_servico k SET ultimo_uso = now(), ultimo_ip = p_ip
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE k.token_hash = p_hash AND k.usuario_id = u.id AND k.revogado_em IS NULL
    AND (k.expira_em IS NULL OR k.expira_em > now()) AND u.ativo AND t.ativo AND NOT u.trocar_senha;
  RETURN QUERY
    SELECT u.id, u.tenant_id, u.login, u.perfil, u.nome, u.email, k.escopos, k.restricao, k.id, k.nome,
           plat.privilegios_de(u.id), u.trocar_senha, k.expira_em, k.revogado_em, k.renovado_por, u.superadmin,
           u.totp_ativo, u.origem, t.slug, t.nome, t.config, u.papel_id
    FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
    WHERE k.token_hash = p_hash AND u.ativo AND t.ativo;
END $$;

-- desafio de 2FA de uso único, 5 min (contexto obrigatório para criar; o hash é o segredo para resolver)
CREATE OR REPLACE FUNCTION plat.auth_desafio_2fa_criar(p_usuario int) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE d text;
BEGIN
  PERFORM plat.contexto_confere(p_usuario);
  d := encode(gen_random_bytes(32), 'hex');
  UPDATE plat.usuario SET desafio_2fa_hash = encode(sha256(convert_to(d, 'UTF8')), 'hex'),
    desafio_2fa_ate = now() + interval '5 minutes' WHERE id = p_usuario;
  RETURN d;
END $$;

CREATE OR REPLACE FUNCTION plat.auth_desafio_2fa_resolver(p_hash text)
RETURNS TABLE (usuario_id int, tenant_id int, login text, nome text, totp_secret text, totp_ativo boolean,
               totp_ultimo_passo bigint, codigos_recuperacao text[], desafio_2fa_ate timestamptz,
               bloqueado_ate timestamptz, ativo boolean, ativo_tenant boolean, config jsonb, superadmin boolean)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT u.id, u.tenant_id, u.login, u.nome, u.totp_secret, u.totp_ativo, u.totp_ultimo_passo, u.codigos_recuperacao,
         u.desafio_2fa_ate, u.bloqueado_ate, u.ativo, t.ativo, t.config, u.superadmin
  FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE u.desafio_2fa_hash = p_hash
$$;

-- única com INSERT em log_acesso; sem contexto aceita o p_tenant resolvido pela API; com contexto, tem de casar
CREATE OR REPLACE FUNCTION plat.log_registrar(p_tenant int, p_usuario int, p_token int, p_ip text, p_metodo text,
  p_rota text, p_status int, p_bytes bigint, p_tempo_ms int, p_agente text, p_resultado text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_tenant IS NOT NULL AND plat.tenant_atual() IS NOT NULL AND p_tenant <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'contexto_de_outro_inquilino';
  END IF;
  BEGIN
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente, resultado)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado);
  EXCEPTION WHEN check_violation THEN
    PERFORM plat.log_particao_garantir(now()::date);
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente, resultado)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado);
  END;
END $$;

-- superadmin resolvido SEMPRE pela sessão (hash), nunca por GUC (achado do T1)
CREATE OR REPLACE FUNCTION plat.plataforma_operador(p_sessao_hash text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE uid int;
BEGIN
  SELECT u.id INTO uid
  FROM plat.sessao s JOIN plat.usuario u ON u.id = s.usuario_id JOIN plat.tenant t ON t.id = u.tenant_id
  WHERE s.token_hash = p_sessao_hash AND u.superadmin AND u.ativo AND t.slug = 'plataforma'
    AND s.expira_em > now() AND coalesce(s.ultimo_uso, s.criado_em) >= now() - interval '24 hours';
  IF uid IS NULL THEN RAISE EXCEPTION 'so_superadmin'; END IF;
  RETURN uid;
END $$;

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
  RETURN QUERY SELECT tid, uid;
END $$;

CREATE OR REPLACE FUNCTION plat.tenant_listar(p_sessao_hash text)
RETURNS TABLE (id int, slug text, nome text, ativo boolean, usuarios bigint, criado_em timestamptz, ultimo_acesso timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT t.id, t.slug, t.nome, t.ativo, count(u.id), t.criado_em, max(u.ultimo_login)
    FROM plat.tenant t LEFT JOIN plat.usuario u ON u.tenant_id = t.id
    GROUP BY t.id ORDER BY t.slug;
END $$;

CREATE OR REPLACE FUNCTION plat.tenant_suspender(p_sessao_hash text, p_id int, p_ativo boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' AND NOT p_ativo THEN RAISE EXCEPTION 'plataforma_nao_suspende'; END IF;
  UPDATE plat.tenant SET ativo = p_ativo WHERE id = p_id;
END $$;

CREATE OR REPLACE FUNCTION plat.plataforma_tenant_id(p_sessao_hash text, p_slug text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE tid int;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  SELECT id INTO tid FROM plat.tenant WHERE slug = p_slug;
  IF tid IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  RETURN tid;
END $$;

-- ---------------------------------------------------------------- permissões (o núcleo do achado do T1)
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA plat FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app;
GRANT SELECT ON plat.privilegio, plat.perfil_privilegio, plat.evento_tipo TO plat_app;
