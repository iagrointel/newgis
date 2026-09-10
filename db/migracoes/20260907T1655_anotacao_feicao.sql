-- 20260907T1655_anotacao_feicao: anotação de usuário ligada a uma feição de camada (item L2-01-k-desenho-anotacoes).
-- Comentário com autor/data, visível aos membros do grupo em que a anotação foi criada, nunca a outro inquilino.
-- Espelha o padrão já usado por plat.item_grupo/plat.grupo_membro (migração 003/011): tenant_id denormalizado
-- para a política não precisar de junção contra a tabela que também tem política (recursão de RLS).

CREATE TABLE IF NOT EXISTS plat.anotacao_feicao (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  camada_id    uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  fid          text NOT NULL CHECK (length(fid) BETWEEN 1 AND 128),
  grupo_id     uuid NOT NULL REFERENCES plat.grupo(id) ON DELETE CASCADE,
  autor_id     int NOT NULL REFERENCES plat.usuario(id),
  texto        text NOT NULL CHECK (length(texto) BETWEEN 1 AND 4000),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  editado_em   timestamptz,
  resolvido    boolean NOT NULL DEFAULT false,
  resolvido_em timestamptz,
  resolvido_por int REFERENCES plat.usuario(id)
);
CREATE INDEX IF NOT EXISTS ix_anotacao_feicao_camada ON plat.anotacao_feicao (camada_id, fid);
CREATE INDEX IF NOT EXISTS ix_anotacao_feicao_grupo ON plat.anotacao_feicao (grupo_id);

-- coerência que a RLS de INSERT não checa sozinha: grupo do MESMO inquilino, camada do MESMO inquilino, e o
-- autor precisa ser membro ativo do grupo (senão a anotação existiria fora do que a leitura consegue mostrar
-- a alguém). Mesma forma de plat.tg_item_grupo (migração 011).
CREATE OR REPLACE FUNCTION plat.tg_anotacao_feicao() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE g plat.grupo;
BEGIN
  SELECT * INTO g FROM plat.grupo WHERE id = NEW.grupo_id;
  IF g.id IS NULL OR g.tenant_id <> NEW.tenant_id OR NEW.tenant_id IS DISTINCT FROM plat.tenant_atual() THEN
    RAISE EXCEPTION 'grupo_de_outro_inquilino';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = NEW.camada_id AND i.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'camada_de_outro_inquilino';
  END IF;
  IF TG_OP = 'INSERT' AND NOT plat.tem('grupos.gerir_todos') THEN
    IF NOT EXISTS (SELECT 1 FROM plat.grupo_membro m
                   WHERE m.grupo_id = g.id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo') THEN
      RAISE EXCEPTION 'sem_contribuicao_no_grupo';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_anotacao_feicao ON plat.anotacao_feicao;
CREATE TRIGGER tg_anotacao_feicao BEFORE INSERT OR UPDATE ON plat.anotacao_feicao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_anotacao_feicao();

ALTER TABLE plat.anotacao_feicao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.anotacao_feicao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_anotacao_feicao_ler ON plat.anotacao_feicao;
CREATE POLICY p_anotacao_feicao_ler ON plat.anotacao_feicao FOR SELECT TO plat_app, plat_leitor
  USING (tenant_id = plat.tenant_atual() AND (
           plat.tem('grupos.gerir_todos')
           OR EXISTS (SELECT 1 FROM plat.grupo_membro m
                      WHERE m.grupo_id = grupo_id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo')));
DROP POLICY IF EXISTS p_anotacao_feicao_inserir ON plat.anotacao_feicao;
CREATE POLICY p_anotacao_feicao_inserir ON plat.anotacao_feicao FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND autor_id = plat.usuario_atual());
DROP POLICY IF EXISTS p_anotacao_feicao_alterar ON plat.anotacao_feicao;
-- autor edita o texto; qualquer membro do grupo (a mesma cláusula de leitura) pode marcar resolvido/reabrir
CREATE POLICY p_anotacao_feicao_alterar ON plat.anotacao_feicao FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (
           autor_id = plat.usuario_atual()
           OR EXISTS (SELECT 1 FROM plat.grupo_membro m
                      WHERE m.grupo_id = grupo_id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo')))
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_anotacao_feicao_apagar ON plat.anotacao_feicao;
CREATE POLICY p_anotacao_feicao_apagar ON plat.anotacao_feicao FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND autor_id = plat.usuario_atual());

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.anotacao_feicao TO plat_app;
GRANT SELECT ON plat.anotacao_feicao TO plat_leitor;
