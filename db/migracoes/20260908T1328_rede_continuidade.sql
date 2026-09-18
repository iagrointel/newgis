-- 20260908T1328_rede_continuidade: CONTINUIDADE DEC/FEC POR CONJUNTO E POR ALIMENTADOR
-- (item L4-10-continuidade-dec-fec).
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
-- depende: 20260906T2126_rede_modelo_elementos.sql
--
-- A ANEEL publica os indicadores coletivos de continuidade por CONJUNTO DE UNIDADES CONSUMIDORAS, não por
-- alimentador e não por transformador. A BDGD, por sua vez, traz o campo CONJ em UNTRMT, UCBT_tab e SSDMT.
-- A chave CONJ é o que liga as duas bases, e é essa junção que este item constrói.
--
-- O que entra aqui:
--   * `rede_continuidade_fonte`  — uma linha por importação: arquivo, resumo criptográfico, quantas linhas
--                                  o arquivo tinha para o recorte pedido e quantas foram gravadas. É onde a
--                                  conferência "contagem = arquivo" fica registrada, não só no log do job;
--   * `rede_continuidade`        — o indicador apurado, por conjunto, indicador, ano e mês. A coluna
--                                  `origem` existe para que a compensação paga possa entrar depois sem
--                                  migração nova; ela NÃO é importada por este item, porque o conjunto de
--                                  dados de compensação da agência usa outro vocabulário de indicador
--                                  (famílias PGU* e QTU*, 96 códigos, nenhum deles DEC ou FEC);
--   * `rede_continuidade_limite` — o limite anual do conjunto por indicador (arquivo de limites da ANEEL).
--
-- Os limites de continuidade por conjunto são estabelecidos na forma do PRODIST Módulo 8, aprovado pela
-- Resolução Normativa ANEEL 956/2021 e seus anexos; os valores usados aqui são os publicados pela própria
-- agência no portal de dados abertos (conjunto de dados "Indicadores coletivos de continuidade DEC e FEC",
-- acesso em 08/09/2026). Nenhum limite é escrito de cabeça no código: todo valor vem do arquivo, e a coluna
-- `fonte_id` diz de qual arquivo veio.
--
-- ⛔ Vocabulário: quando o apurado passa do limite, o produto diz "acima do limite regulatório" com o
-- número e o limite ao lado. A palavra de acusação não é usada em lugar nenhum deste item: o cálculo do
-- que é infração, e a sua consequência, são do processo da agência, não desta leitura.
--
-- Tudo é dado do inquilino (tenant_id + RLS), como o resto da linha L4. Idempotente. Sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.rede_continuidade_fonte (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  arquivo          text NOT NULL CHECK (btrim(arquivo) <> '' AND length(arquivo) <= 1024),
  especie          text NOT NULL CHECK (especie IN ('apurado', 'compensacao', 'limite')),  -- 'compensacao' reservado
  sha256           text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  bytes            bigint CHECK (bytes IS NULL OR bytes >= 0),
  conjuntos        int[] NOT NULL DEFAULT '{}',
  ano_de           smallint,
  ano_ate          smallint,
  linhas_arquivo   bigint NOT NULL DEFAULT 0 CHECK (linhas_arquivo >= 0),
  linhas_gravadas  bigint NOT NULL DEFAULT 0 CHECK (linhas_gravadas >= 0),
  importado_em     timestamptz NOT NULL DEFAULT now(),
  job_id           uuid,
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_continuidade_fonte_tenant ON plat.rede_continuidade_fonte (tenant_id);

-- o indicador apurado. `periodo` é o mês (1..12) como a ANEEL publica; o valor do ANO é a soma dos meses,
-- e é feita na leitura, para que a base guarde o dado como veio do arquivo.
CREATE TABLE IF NOT EXISTS plat.rede_continuidade (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  conjunto_id    int NOT NULL,
  conjunto_nome  text,
  agente         text,
  cnpj           text CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{1,14}$'),
  indicador      text NOT NULL CHECK (indicador IN ('DEC', 'FEC')),
  origem         text NOT NULL CHECK (origem IN ('apurado', 'compensacao')),
  ano            smallint NOT NULL CHECK (ano BETWEEN 1990 AND 2100),
  periodo        smallint NOT NULL CHECK (periodo BETWEEN 1 AND 12),
  valor          double precision NOT NULL CHECK (valor >= 0),
  fonte_id       uuid,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, conjunto_id, indicador, origem, ano, periodo)
);
CREATE INDEX IF NOT EXISTS ix_rede_continuidade_tenant ON plat.rede_continuidade (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_continuidade_conjunto
  ON plat.rede_continuidade (tenant_id, conjunto_id, ano);
ALTER TABLE plat.rede_continuidade DROP CONSTRAINT IF EXISTS rede_continuidade_tenant_fonte_fkey;
ALTER TABLE plat.rede_continuidade ADD CONSTRAINT rede_continuidade_tenant_fonte_fkey
  FOREIGN KEY (tenant_id, fonte_id) REFERENCES plat.rede_continuidade_fonte (tenant_id, id) ON DELETE SET NULL;

-- limite anual por conjunto e indicador (PRODIST Módulo 8 / REN 956/2021, valores publicados pela ANEEL).
CREATE TABLE IF NOT EXISTS plat.rede_continuidade_limite (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  conjunto_id  int NOT NULL,
  indicador    text NOT NULL CHECK (indicador IN ('DEC', 'FEC')),
  ano          smallint NOT NULL CHECK (ano BETWEEN 1990 AND 2100),
  valor        double precision NOT NULL CHECK (valor >= 0),
  fonte_id     uuid,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, conjunto_id, indicador, ano)
);
CREATE INDEX IF NOT EXISTS ix_rede_continuidade_limite_tenant ON plat.rede_continuidade_limite (tenant_id);
ALTER TABLE plat.rede_continuidade_limite DROP CONSTRAINT IF EXISTS rede_continuidade_limite_tenant_fonte_fkey;
ALTER TABLE plat.rede_continuidade_limite ADD CONSTRAINT rede_continuidade_limite_tenant_fonte_fkey
  FOREIGN KEY (tenant_id, fonte_id) REFERENCES plat.rede_continuidade_fonte (tenant_id, id) ON DELETE SET NULL;

-- RLS: mesmo padrão das demais tabelas da linha L4 (20260906T1553).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_continuidade_fonte','rede_continuidade','rede_continuidade_limite'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/continuidade_importar', 'continuidade DEC/FEC importada da ANEEL (arquivo, linhas do arquivo e gravadas)'),
  ('redes/continuidade_apagar', 'continuidade DEC/FEC do inquilino apagada (conjuntos afetados)')
ON CONFLICT (nome) DO NOTHING;
