-- Item L2-02-e-simbolos-sprites-glifos: ícone SVG enviado pelo inquilino, para entrar no sprite dele.
-- Ponytail: o conteúdo SVG já saneado (app/simbolos/validador.py) é pequeno (<= 64 kB, portão do item) e
-- cabe direto numa coluna text — evita depender de armazenamento de objeto (item L0-11, ainda PARCIAL) só
-- para um arquivo tão pequeno; recurso nativo da plataforma (Postgres) em vez de nova infraestrutura.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.simbolo_upload (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  nome          text NOT NULL CHECK (nome ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  categoria     text NOT NULL DEFAULT 'personalizado' CHECK (length(categoria) BETWEEN 1 AND 40),
  conteudo_svg  text NOT NULL CHECK (length(conteudo_svg) BETWEEN 1 AND 65536),
  bytes         int NOT NULL CHECK (bytes > 0 AND bytes <= 65536),
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  criado_por    int NOT NULL REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_simbolo_upload_tenant ON plat.simbolo_upload (tenant_id);

ALTER TABLE plat.simbolo_upload ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_simbolo_upload ON plat.simbolo_upload;
CREATE POLICY p_simbolo_upload ON plat.simbolo_upload FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
-- GRANT vem do ALTER DEFAULT PRIVILEGES de 001_fundacao.sql (mesmo papel plat_app de toda tabela nova).
