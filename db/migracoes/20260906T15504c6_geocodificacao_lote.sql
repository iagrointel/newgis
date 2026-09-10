-- 20260906T15504c6_geocodificacao_lote: geocodificar uma tabela enviada pelo usuário (item
-- L2-11-a-geocodificacao-csv). O motor de UM endereço já existe (migração 045, item L2-11-b); aqui entra o
-- LOTE: o arquivo (CSV/TXT/XLSX) enviado, o mapeamento de colunas escolhido pelo usuário, uma linha de
-- resultado POR LINHA DO ARQUIVO com pontuação e tipo de acerto, e a revisão manual do que não resolveu.
--
-- Duas tabelas, por inquilino (P6 se aplica: o arquivo é do dono do token, ao contrário de plat.geo_* que é
-- referência aberta):
--   plat.geocodificacao        -> o lote (arquivo, mapeamento, estado, contagens, base de endereços usada)
--   plat.geocodificacao_linha  -> uma linha por linha do arquivo, inclusive as MALFORMADAS (estado próprio,
--                                 com motivo): linha ruim não derruba o trabalho todo, fica registrada.
-- `origem` separa o que a máquina resolveu do que o humano arrastou no mapa ('automatica' x 'manual'); é a
-- coluna que a camada publicada carrega, para nunca se perder qual ponto é medido e qual é declarado.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.geocodificacao (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  usuario_id      int NOT NULL REFERENCES plat.usuario(id),
  arquivo_id      uuid NOT NULL REFERENCES plat.item(id),
  item_id         uuid,                       -- camada de pontos publicada (preenchida ao concluir)
  titulo          text NOT NULL CHECK (length(titulo) BETWEEN 1 AND 250),
  mapeamento      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {coluna_de: nome no arquivo} por campo de endereço
  estado          text NOT NULL DEFAULT 'na_fila'
                  CHECK (estado IN ('na_fila','rodando','concluida','falhou','cancelada')),
  linhas_total    int NOT NULL DEFAULT 0,
  resolvidas      int NOT NULL DEFAULT 0,
  pendentes       int NOT NULL DEFAULT 0,
  malformadas     int NOT NULL DEFAULT 0,
  manuais         int NOT NULL DEFAULT 0,
  resumo          jsonb NOT NULL DEFAULT '{}'::jsonb,   -- contagem por tipo_acerto + tempo medido
  base_enderecos  jsonb NOT NULL DEFAULT '{}'::jsonb,   -- ficha de proveniência da base (plat.geo_instalacao)
  job_id          uuid,
  erro            text,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_geocodificacao_tenant ON plat.geocodificacao (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_geocodificacao_arquivo ON plat.geocodificacao (arquivo_id);

CREATE TABLE IF NOT EXISTS plat.geocodificacao_linha (
  geocodificacao_id uuid NOT NULL REFERENCES plat.geocodificacao(id) ON DELETE CASCADE,
  n                 int NOT NULL,             -- número da linha NO ARQUIVO (1 = 1ª linha de dado, sem cabeçalho)
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  entrada           jsonb NOT NULL DEFAULT '{}'::jsonb,  -- os campos de endereço lidos do arquivo
  endereco          text,                     -- endereço devolvido pelo geocodificador (o que casou)
  lon               double precision,
  lat               double precision,
  score             double precision,
  tipo_acerto       text,
  origem            text CHECK (origem IN ('automatica','manual')),
  estado            text NOT NULL DEFAULT 'pendente'
                    CHECK (estado IN ('resolvida','pendente','malformada')),
  motivo            text,                     -- por que ficou pendente/malformada (texto do usuário)
  avisos            jsonb NOT NULL DEFAULT '[]'::jsonb,
  cod_municipio     int,
  municipio         text,
  uf                text,
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (geocodificacao_id, n)
);
CREATE INDEX IF NOT EXISTS ix_geocodificacao_linha_estado
  ON plat.geocodificacao_linha (geocodificacao_id, estado, n);

ALTER TABLE plat.geocodificacao       ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.geocodificacao_linha ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.geocodificacao       FORCE ROW LEVEL SECURITY;
ALTER TABLE plat.geocodificacao_linha FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_geocodificacao ON plat.geocodificacao;
CREATE POLICY p_geocodificacao ON plat.geocodificacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_geocodificacao_linha ON plat.geocodificacao_linha;
CREATE POLICY p_geocodificacao_linha ON plat.geocodificacao_linha FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.geocodificacao       TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.geocodificacao_linha TO plat_app;

-- tipos de evento do item (plat.evento tem chave estrangeira para plat.evento_tipo: sem esta linha a rota
-- levanta ForeignKeyViolation na primeira criação — achado desta sessão, no primeiro job que rodou de verdade)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('geocodificacoes/criar', 'lote de geocodificação de tabela criado a partir de um arquivo (L2-11-a)'),
  ('geocodificacoes/concluir', 'lote de geocodificação concluído e camada de pontos publicada (L2-11-a)'),
  ('geocodificacoes/ponto_manual', 'coordenada de uma linha gravada à mão na tela de revisão (L2-11-a)'),
  ('geocodificacoes/regeocodificar', 'lote de geocodificação refeito só nas linhas pendentes (L2-11-a)')
ON CONFLICT (nome) DO NOTHING;
