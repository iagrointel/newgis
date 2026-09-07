-- tile_leitura: contagem de leitura de ladrilho por token (item L1-02-tiles-token, cláusula "registro com
-- contagem por token"). Uma linha por (inquilino, token, item, dia): um serviço de tile faz milhares de
-- leituras por minuto e uma linha por ladrilho em `plat.log_acesso` inutilizaria a tabela de auditoria — o
-- agregado é escrito por lote (app/imagens/leitura.py) com `ON CONFLICT DO UPDATE`.
-- O que NUNCA entra aqui: o token em claro (só o `token_id`, como em `plat.log_acesso`) e endereço de quem lê.
CREATE TABLE IF NOT EXISTS plat.tile_leitura (
  tenant_id   int  NOT NULL REFERENCES plat.tenant(id),
  token_id    int  NOT NULL REFERENCES plat.token_servico(id) ON DELETE CASCADE,
  item        text NOT NULL,
  dia         date NOT NULL,
  ladrilhos   bigint NOT NULL DEFAULT 0,
  bytes       bigint NOT NULL DEFAULT 0,
  erros       bigint NOT NULL DEFAULT 0,
  primeiro_em timestamptz NOT NULL DEFAULT now(),
  ultimo_em   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, token_id, item, dia)
);
CREATE INDEX IF NOT EXISTS ix_tile_leitura_tenant_dia ON plat.tile_leitura (tenant_id, dia DESC);

ALTER TABLE plat.tile_leitura ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_tile_leitura ON plat.tile_leitura;
-- leitura pelo próprio inquilino; escrita SÓ pela função SECURITY DEFINER abaixo (mesmo desenho de log_acesso:
-- quem serve o ladrilho não tem contexto de inquilino na conexão, serve com a credencial do processo)
CREATE POLICY p_tile_leitura ON plat.tile_leitura FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
REVOKE INSERT, UPDATE, DELETE ON plat.tile_leitura FROM plat_app;

CREATE OR REPLACE FUNCTION plat.tile_leitura_registrar(
  p_tenant int, p_token int, p_item text, p_dia date, p_ladrilhos bigint, p_bytes bigint, p_erros bigint
) RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.tile_leitura(tenant_id, token_id, item, dia, ladrilhos, bytes, erros)
  VALUES (p_tenant, p_token, left(p_item, 128), p_dia, greatest(p_ladrilhos, 0), greatest(p_bytes, 0),
          greatest(p_erros, 0))
  ON CONFLICT (tenant_id, token_id, item, dia) DO UPDATE SET
    ladrilhos = plat.tile_leitura.ladrilhos + excluded.ladrilhos,
    bytes     = plat.tile_leitura.bytes + excluded.bytes,
    erros     = plat.tile_leitura.erros + excluded.erros,
    ultimo_em = now()
$$;
REVOKE ALL ON FUNCTION plat.tile_leitura_registrar(int, int, text, date, bigint, bigint, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tile_leitura_registrar(int, int, text, date, bigint, bigint, bigint) TO plat_app;
