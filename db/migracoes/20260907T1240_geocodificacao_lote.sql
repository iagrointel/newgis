-- Item L2-11-a-geocodificacao-csv: proveniência e resumo do job `geocodificador.lote_csv` (a camada de pontos em
-- si é uma tabela dinâmica d_<slug>.c_<uuid16>, criada pela própria tarefa — mesma máquina do L0-04-c). Esta
-- tabela guarda o que a camada sozinha não guarda: o MAPEAMENTO de coluna usado, o limiar de pendência e a ficha
-- de proveniência da base de endereços (join com plat.geo_instalacao no momento do job — se a base for reinstalada
-- depois, a ficha gravada aqui continua descrevendo a versão realmente usada, não a versão atual).
CREATE TABLE IF NOT EXISTS plat.geocodificacao_lote (
  item_id         uuid PRIMARY KEY REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  mapeamento      jsonb NOT NULL,
  limiar_pendente numeric NOT NULL,
  proveniencia    jsonb NOT NULL,
  resumo          jsonb NOT NULL,
  criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_geocodificacao_lote_tenant ON plat.geocodificacao_lote (tenant_id, criado_em DESC);

ALTER TABLE plat.geocodificacao_lote ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_geocodificacao_lote ON plat.geocodificacao_lote;
CREATE POLICY p_geocodificacao_lote ON plat.geocodificacao_lote FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.geocodificacao_lote TO plat_app;
