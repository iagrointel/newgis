-- 20260908T1225_versionamento_por_ramo: item L2-13-a-versoes-ramo-reconciliar. Versionamento por RAMO
-- (equivalente ao branch versioning do ArcGIS Enterprise) nas camadas marcadas como versionadas.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 20260907T1025_historico_feicao.sql
--
-- DECISÃO DE DESENHO (ADR 20260908T1240): o ramo NÃO acrescenta coluna à tabela de camada. As linhas do
-- ramo vivem numa tabela COMPANHEIRA `d_<slug>.c_<uuid16>__ramo`, com as mesmas colunas da camada mais
-- `versao_id`, `momento_inicio`, `momento_fim` e `apagada`; a versão PADRÃO continua sendo a própria
-- tabela da camada, e o "momento" de cada linha do padrão vem de `plat.feicao_historico`
-- (20260907T1025, item L2-03-d), que já grava atributos e geometria de antes e depois de toda escrita,
-- inclusive a que não passa pela API.
--
-- Por que não pôr `versao_id`/`momento_fim` na própria tabela da camada, como diz a hipótese do item:
-- todo caminho de leitura que já existe (motor de consulta do FeatureServer, OGC API Features, WFS,
-- tiles do Martin, exportação, união/divisão de feição, anexos) lê a tabela SEM filtro de versão. Com as
-- colunas na tabela da camada, cada um desses caminhos passaria a ver as linhas de ramo até ser
-- corrigido um a um, e a cláusula "leitura no ramo antes do post não vaza para o padrão" dependeria de
-- lembrar de todos. Com a tabela companheira o não-vazamento é ESTRUTURAL: quem não sabe de ramo lê a
-- tabela da camada e vê exatamente o padrão. O preço é o `UNION ALL` da leitura no ramo, feito em
-- app/versoes/leitura.py.

-- ---------------------------------------------------------------- catálogo de ramos
CREATE TABLE IF NOT EXISTS plat.versao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int  NOT NULL,
  item_id        uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  nome           text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128),
  dono_id        int  NOT NULL,
  acesso         text NOT NULL DEFAULT 'protegido' CHECK (acesso IN ('privado', 'protegido', 'publico')),
  -- pai NULL = o padrão (SDE.DEFAULT). Ramo de ramo não é oferecido nesta versão: a Esri permite,
  -- mas reconciliar em cadeia multiplica o número de estados a comparar e o item não pede.
  pai            uuid REFERENCES plat.versao(id) ON DELETE SET NULL,
  descricao      text,
  criada_em      timestamptz NOT NULL DEFAULT now(),
  -- `momento` é o momento BASE: o instante do padrão contra o qual este ramo é lido e reconciliado.
  -- Nasce igual a criada_em e avança quando o ramo é reconciliado (aceita o padrão de então) ou
  -- rebaseado depois de publicar.
  momento        timestamptz NOT NULL DEFAULT now(),
  reconciliada_em timestamptz,
  publicada_em   timestamptz,
  estado         text NOT NULL DEFAULT 'aberta' CHECK (estado IN ('aberta', 'publicada', 'apagada')),
  apagada_em     timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_versao_nome_viva
  ON plat.versao (tenant_id, item_id, lower(nome)) WHERE estado <> 'apagada';
CREATE INDEX IF NOT EXISTS ix_versao_item ON plat.versao (tenant_id, item_id, estado);

ALTER TABLE plat.versao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.versao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_versao ON plat.versao;
CREATE POLICY p_versao ON plat.versao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.versao TO plat_app;

-- ---------------------------------------------------------------- conflitos detectados e a decisão tomada
-- Uma linha por feição em conflito, por ramo. `momento_padrao` é o instante da ÚLTIMA alteração do padrão
-- naquela feição no momento da detecção: se o padrão mudar de novo depois de a decisão ter sido tomada, o
-- conflito REABRE (a resolução deixa de valer), e é isso que impede publicar sobre um padrão que andou.
CREATE TABLE IF NOT EXISTS plat.versao_conflito (
  id             bigserial PRIMARY KEY,
  tenant_id      int  NOT NULL,
  versao_id      uuid NOT NULL REFERENCES plat.versao(id) ON DELETE CASCADE,
  globalid       uuid NOT NULL,
  tipo           text NOT NULL CHECK (tipo IN ('atualizar-atualizar', 'atualizar-apagar', 'apagar-atualizar',
                                               'inserir-inserir')),
  detalhe        jsonb NOT NULL DEFAULT '{}'::jsonb,
  momento_padrao timestamptz,
  detectado_em   timestamptz NOT NULL DEFAULT now(),
  decisao        text CHECK (decisao IN ('ramo', 'padrao', 'manual')),
  resolvido_em   timestamptz,
  resolvido_por  int
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_versao_conflito ON plat.versao_conflito (versao_id, globalid);
ALTER TABLE plat.versao_conflito ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.versao_conflito FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_versao_conflito ON plat.versao_conflito;
CREATE POLICY p_versao_conflito ON plat.versao_conflito FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.versao_conflito TO plat_app;
GRANT USAGE ON SEQUENCE plat.versao_conflito_id_seq TO plat_app;

-- ---------------------------------------------------------------- tabela companheira de ramo
-- SECURITY DEFINER porque emite DDL em schema de dado do inquilino (mesmo motivo de plat.camada_preparar).
-- Trinco de aconselhamento por transação ANTES do DDL (ADR 0025): CREATE TABLE e GRANT atualizam linha de
-- catálogo sem bloqueio pesado, e duas sessões do mesmo inquilino versionando a mesma camada ao mesmo
-- tempo colidiriam com `tuple concurrently updated`. Chave por schema.tabela: camadas diferentes não
-- esperam uma pela outra.
CREATE OR REPLACE FUNCTION plat.camada_versionar(p_schema text, p_tabela text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; ramo text; nome_curto text;
BEGIN
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = t_atual AND 'd_' || slug = p_schema) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  IF to_regclass(format('%I.%I', p_schema, p_tabela)) IS NULL THEN
    RAISE EXCEPTION 'camada_inexistente';
  END IF;
  ramo := p_tabela || '__ramo';
  nome_curto := substr(p_tabela, 3);
  PERFORM pg_advisory_xact_lock(hashtext('camada_versionar:' || p_schema || '.' || p_tabela));

  IF to_regclass(format('%I.%I', p_schema, ramo)) IS NULL THEN
    -- INCLUDING DEFAULTS de propósito, sem INCLUDING ALL: a chave primária de `fid` e a unicidade de
    -- `globalid` NÃO valem aqui (a mesma feição tem uma linha por ramo, e mais de uma quando o ramo já
    -- fechou uma versão anterior dela). O `fid` continua saindo da MESMA sequência da camada, então o
    -- OBJECTID visto no ramo nunca colide com o do padrão.
    EXECUTE format(
      'CREATE TABLE %1$I.%2$I ('
      '  LIKE %1$I.%3$I INCLUDING DEFAULTS, '
      '  versao_id      uuid NOT NULL, '
      '  momento_inicio timestamptz NOT NULL DEFAULT now(), '
      '  momento_fim    timestamptz, '
      '  apagada        boolean NOT NULL DEFAULT false, '
      '  ramo_pk        bigserial PRIMARY KEY)',
      p_schema, ramo, p_tabela
    );
  END IF;
  EXECUTE format('CREATE INDEX IF NOT EXISTS r_%2$s_vigente ON %1$I.%3$I (versao_id, globalid) '
                 'WHERE momento_fim IS NULL', p_schema, nome_curto, ramo);
  EXECUTE format('CREATE INDEX IF NOT EXISTS r_%2$s_globalid ON %1$I.%3$I (versao_id, globalid)',
                 p_schema, nome_curto, ramo);
  EXECUTE format('ALTER TABLE %1$I.%2$I ENABLE ROW LEVEL SECURITY', p_schema, ramo);
  EXECUTE format('ALTER TABLE %1$I.%2$I FORCE ROW LEVEL SECURITY', p_schema, ramo);
  EXECUTE format('DROP POLICY IF EXISTS p_r_%2$s ON %1$I.%3$I', p_schema, nome_curto, ramo);
  EXECUTE format(
    'CREATE POLICY p_r_%2$s ON %1$I.%3$I FOR ALL TO plat_app, plat_leitor '
    'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())',
    p_schema, nome_curto, ramo
  );
  EXECUTE format('DROP TRIGGER IF EXISTS tg_tenant ON %1$I.%2$I', p_schema, ramo);
  EXECUTE format('CREATE TRIGGER tg_tenant BEFORE INSERT ON %1$I.%2$I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir()', p_schema, ramo);
  EXECUTE format('COMMENT ON TABLE %1$I.%2$I IS %3$L', p_schema, ramo,
                 'plat linhas de ramo da camada versionada (L2-13-a)');
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %1$I.%2$I TO plat_app', p_schema, ramo);
  EXECUTE format('GRANT SELECT ON %1$I.%2$I TO plat_leitor', p_schema, ramo);
  EXECUTE format('GRANT USAGE ON SEQUENCE %1$I.%2$I TO plat_app', p_schema, ramo || '_ramo_pk_seq');
  RETURN ramo;
END $$;
REVOKE ALL ON FUNCTION plat.camada_versionar(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_versionar(text, text) TO plat_app;

-- ---------------------------------------------------------------- eventos de domínio
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('camadas/versionar',  'camada marcada como versionada por ramo (L2-13-a)'),
  ('versoes/criar',      'ramo de versão criado sobre o padrão da camada (L2-13-a)'),
  ('versoes/reconciliar','ramo reconciliado contra o padrão; conflitos detectados (L2-13-a)'),
  ('versoes/resolver',   'conflito de reconciliação resolvido (ramo/padrão/manual) (L2-13-a)'),
  ('versoes/publicar',   'ramo publicado no padrão (post) (L2-13-a)'),
  ('versoes/apagar',     'ramo descartado com as suas edições (L2-13-a)')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- esquema de camada_vetorial: v3 -> v4
-- Acrescenta só a propriedade OPCIONAL `versionamento` (o esquema é additionalProperties:false, então sem
-- este passo marcar a camada como versionada seria recusado pela validação do catálogo). jsonb_set em vez de
-- reescrever o esquema inteiro: o arquivo que o definiu (20260906T1859) segue sendo a fonte do resto, e duas
-- trilhas que acrescentem propriedades diferentes não se apagam.
UPDATE plat.tipo_item
   SET esquema = jsonb_set(
         esquema, '{properties,versionamento}',
         '{"type":"object","additionalProperties":false,
           "properties":{"habilitado":{"type":"boolean"},
                         "tabela_ramo":{"type":"string","pattern":"^c_[0-9a-f]{16}__ramo$"},
                         "ramos_max":{"type":"integer","minimum":1,"maximum":200}}}'::jsonb, true),
       esquema_versao = 4
 WHERE nome = 'camada_vetorial' AND esquema_versao < 4;
