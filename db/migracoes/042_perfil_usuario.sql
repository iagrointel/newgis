-- Migração 042 — perfil próprio do usuário (item L0-02-g-perfil-usuario): colunas novas em plat.usuario para
-- as preferências que o item filho existe para resolver — idioma, unidades, formato de data, foto (reaproveita
-- app/objetos.py, classe usuario_foto, MESMO padrão de plat.tenant.config->logo do L0-07-a: sha256 numa coluna,
-- objeto de verdade no Garage) e visibilidade do perfil. O pai (L0-02-tenant-auth) já cobre nome/e-mail/senha/
-- 2FA/sessões/convites/tokens em app/auth/rotas_eu.py; esta migração só acrescenta o que faltava (0 ocorrência
-- de idioma_preferido/unidades/formato_data/foto_perfil/visibilidade_perfil antes desta migração, conferido por
-- grep — ver handoffs/T3/L0-02g-L0-05c.md).
-- PERFIL_IDIOMAS ('pt-BR','en','es') é maior que ORG_IDIOMAS (só 'pt-BR' hoje): a hipótese do item já guarda a
-- preferência agora; a APLICAÇÃO da tradução em tela é o item L7-10-a-i18n-pt-en-es, ainda pendente. Guardar o
-- valor não promete tela traduzida hoje.
-- Idempotente; sem BEGIN/COMMIT.

ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS idioma_preferido    text NOT NULL DEFAULT 'pt-BR';
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS unidades            text NOT NULL DEFAULT 'metrico';
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS formato_data        text NOT NULL DEFAULT 'dd/mm/aaaa';
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS visibilidade_perfil text NOT NULL DEFAULT 'inquilino';
ALTER TABLE plat.usuario ADD COLUMN IF NOT EXISTS foto_sha256         text;  -- NULL = sem foto; 64 hex quando há

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_idioma_preferido') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_idioma_preferido CHECK (idioma_preferido IN ('pt-BR','en','es'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_unidades') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_unidades CHECK (unidades IN ('metrico','imperial'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_formato_data') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_formato_data
      CHECK (formato_data IN ('dd/mm/aaaa','mm/dd/aaaa','aaaa-mm-dd'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_visibilidade_perfil') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_visibilidade_perfil CHECK (visibilidade_perfil IN ('privado','inquilino'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_usuario_foto_sha256') THEN
    ALTER TABLE plat.usuario ADD CONSTRAINT ck_usuario_foto_sha256 CHECK (foto_sha256 IS NULL OR foto_sha256 ~ '^[0-9a-f]{64}$');
  END IF;
END $$;

-- vocabulário novo de evento (append à tabela existente da 003; ON CONFLICT preserva reaplicação)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('usuarios/foto_enviar', 'foto de perfil enviada pelo próprio usuário (reaproveita plat.arquivo, classe usuario_foto)'),
  ('usuarios/foto_remover', 'foto de perfil removida pelo próprio usuário')
ON CONFLICT (nome) DO NOTHING;
