-- 20260907T1645_intercambio_lote_importacao: item L6-02-o-importacao-exportacao-formatos, metade
-- IMPORTAÇÃO. plat.importacao (029) já é o funil de 1 arquivo; aqui só o AGRUPAMENTO de várias em uma
-- chamada — nenhuma coluna nova de domínio, nenhum conversor novo. plat.intercambio_lote_importacao
-- guarda o total pedido e serve de âncora para `GET /api/intercambio/importacoes-lote/{id}`; a coluna
-- `lote_id` em plat.importacao (nullable: importação avulsa continua sem lote) é o que agrupa.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.intercambio_lote_importacao (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int         NOT NULL REFERENCES plat.tenant(id),
  usuario_id    int         REFERENCES plat.usuario(id),
  total         int         NOT NULL CHECK (total > 0),
  criado_em     timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE plat.importacao ADD COLUMN IF NOT EXISTS lote_id uuid REFERENCES plat.intercambio_lote_importacao(id);
CREATE INDEX IF NOT EXISTS ix_importacao_lote ON plat.importacao (lote_id) WHERE lote_id IS NOT NULL;

ALTER TABLE plat.intercambio_lote_importacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_intercambio_lote_importacao ON plat.intercambio_lote_importacao;
CREATE POLICY p_intercambio_lote_importacao ON plat.intercambio_lote_importacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

CREATE OR REPLACE FUNCTION plat.intercambio_lote_importacao_tenant() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS NULL THEN
    NEW.tenant_id := plat.tenant_atual();
  END IF;
  IF NEW.tenant_id IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS intercambio_lote_importacao_tenant ON plat.intercambio_lote_importacao;
CREATE TRIGGER intercambio_lote_importacao_tenant BEFORE INSERT ON plat.intercambio_lote_importacao
  FOR EACH ROW EXECUTE FUNCTION plat.intercambio_lote_importacao_tenant();
REVOKE EXECUTE ON FUNCTION plat.intercambio_lote_importacao_tenant() FROM PUBLIC, plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('intercambio/importar_lote', 'lote de importações criado em uma chamada (L6-02-o)')
ON CONFLICT (nome) DO NOTHING;
