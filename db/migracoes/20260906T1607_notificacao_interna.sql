-- 20260906T1607_notificacao_interna: metade do item L0-03-k que não existia (achado G2-7 do adversário do grupo
-- G2: nenhuma rota, tabela, migração ou linha de código de notificação interna). Notificação por usuário, com
-- lida/não lida, dedup por chave, sino na barra e expurgo por idade. O ADR 0004 seção 8.5 dizia que a fonte
-- seria `plat.evento` lido pelo L0-10; aqui a notificação é ESCRITA na mesma transação de quem a origina
-- (convite de grupo) ou pelo worker ao terminar o job, porque o L0-10 não entrega leitura de `evento` por
-- usuário e uma tela que promete sino não pode depender de item que ainda não existe.
-- Idempotente; sem BEGIN/COMMIT (padrão da linha).

CREATE TABLE IF NOT EXISTS plat.notificacao (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  usuario_id  int  NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  tipo        text NOT NULL CHECK (tipo ~ '^[a-z_]+/[a-z_]+$'),
  titulo      text NOT NULL CHECK (length(titulo) BETWEEN 1 AND 250),
  corpo       text CHECK (corpo IS NULL OR length(corpo) <= 1000),
  url         text CHECK (url IS NULL OR (length(url) <= 500 AND url LIKE '/%')),
  alvo_tipo   text CHECK (alvo_tipo IS NULL OR alvo_tipo IN ('item','pasta','grupo','job','usuario','token')),
  alvo_id     text CHECK (alvo_id IS NULL OR length(alvo_id) <= 64),
  chave       text NOT NULL CHECK (length(chave) BETWEEN 1 AND 200),
  criado_em   timestamptz NOT NULL DEFAULT now(),
  lida_em     timestamptz
);
-- dedup: a MESMA chave para o MESMO usuário nunca vira duas linhas (padrão ux_notif_chave do SIG de teste interno)
CREATE UNIQUE INDEX IF NOT EXISTS ux_notificacao_chave ON plat.notificacao (usuario_id, chave);
-- o sino: contagem de não lidas por usuário (índice parcial: só as não lidas entram)
CREATE INDEX IF NOT EXISTS ix_notificacao_sino ON plat.notificacao (usuario_id) WHERE lida_em IS NULL;
-- a lista e o expurgo por idade
CREATE INDEX IF NOT EXISTS ix_notificacao_lista ON plat.notificacao (usuario_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_notificacao_idade ON plat.notificacao (criado_em);

ALTER TABLE plat.notificacao ENABLE ROW LEVEL SECURITY;
-- ler/marcar/apagar: SÓ as próprias (a refutação pede "ler notificação de outro por id" = 404).
DROP POLICY IF EXISTS p_notificacao_propria ON plat.notificacao;
CREATE POLICY p_notificacao_propria ON plat.notificacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual())
  WITH CHECK (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual());
-- escrever PARA outro usuário do mesmo inquilino (quem convida notifica o convidado): política só de INSERT,
-- sem USING, então continua não sendo possível LER nem alterar a linha do outro.
DROP POLICY IF EXISTS p_notificacao_criar ON plat.notificacao;
CREATE POLICY p_notificacao_criar ON plat.notificacao FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual()
              AND EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = usuario_id AND u.tenant_id = plat.tenant_atual()));
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.notificacao TO plat_app;

-- ---------------------------------------------------------------- criação com teto por minuto e dedup por chave
-- SECURITY DEFINER porque o worker (role plat_worker, sem privilégio de tabela) também notifica ao terminar o
-- job. Devolve o id criado, NULL quando a chave repete ou quando o teto por minuto foi atingido (o teto é a
-- resposta à refutação "10 mil notificações para um usuário em 1 min"). Padrão de REVOKE da 011.
CREATE OR REPLACE FUNCTION plat.notificar(
  p_tenant int, p_usuario int, p_tipo text, p_titulo text, p_chave text,
  p_corpo text DEFAULT NULL, p_url text DEFAULT NULL, p_alvo_tipo text DEFAULT NULL, p_alvo_id text DEFAULT NULL,
  p_teto_minuto int DEFAULT 60)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE novo uuid; n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = p_usuario AND u.tenant_id = p_tenant) THEN
    RAISE EXCEPTION 'notificacao_usuario_fora_do_inquilino';
  END IF;
  SELECT count(*) INTO n FROM plat.notificacao
   WHERE usuario_id = p_usuario AND criado_em > now() - interval '1 minute';
  IF n >= p_teto_minuto THEN
    RETURN NULL;
  END IF;
  INSERT INTO plat.notificacao(tenant_id, usuario_id, tipo, titulo, corpo, url, alvo_tipo, alvo_id, chave)
  VALUES (p_tenant, p_usuario, p_tipo, left(p_titulo, 250), left(p_corpo, 1000), p_url, p_alvo_tipo, p_alvo_id, p_chave)
  ON CONFLICT (usuario_id, chave) DO NOTHING
  RETURNING id INTO novo;
  RETURN novo;
END $$;
REVOKE ALL ON FUNCTION plat.notificar(int,int,text,text,text,text,text,text,text,int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.notificar(int,int,text,text,text,text,text,text,text,int) TO plat_app;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_worker') THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION plat.notificar(int,int,text,text,text,text,text,text,text,int) TO plat_worker';
  END IF;
END $$;

-- ---------------------------------------------------------------- expurgo por idade (90 dias, periódico)
-- Mesma disciplina de plat.lixeira_expurgar: fora do inquilino técnico `plataforma`, só o inquilino do contexto.
CREATE OR REPLACE FUNCTION plat.notificacoes_expurgar(p_dias int DEFAULT 90, p_agora timestamptz DEFAULT now())
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual(); n int;
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  IF p_dias < 1 THEN RAISE EXCEPTION 'notificacao_expurgo_dias_invalido'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  DELETE FROM plat.notificacao
   WHERE criado_em < p_agora - make_interval(days => p_dias) AND (t_plataforma OR tenant_id = t_ctx);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION plat.notificacoes_expurgar(int, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.notificacoes_expurgar(int, timestamptz) TO plat_app;

-- tipos de evento das rotas de escrita deste pedaço
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('notificacoes/lida', 'notificação marcada como lida (uma ou todas)')
ON CONFLICT (nome) DO NOTHING;
