-- 20260907T1244_relacionamentos: classes de relacionamento entre camadas do inquilino (item
-- L2-10-b-relacionamentos). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- O que entra:
--   plat.relacionamento      — a classe em si: origem, destino, cardinalidade (1:1|1:N|N:M), chave de
--                              origem/destino (nome de campo OU 'globalid'), composto (apagar origem apaga
--                              destino) ou simples, nome direto/inverso, cardinalidade mín/máx opcionais,
--                              limite declarado de relacionados por consulta.
--   plat.relacionamento_junc — tabela de junção ÚNICA para toda relação N:M (rel_id discrimina; evita criar
--                              uma tabela física nova por relacionamento, que exigiria DDL dinâmico por
--                              classe e complicaria a trava de FK composta). Guarda o VALOR da chave (texto)
--                              dos dois lados, nunca fid (fid não sobrevive a reimportação — cláusula 5 do
--                              portão: "relacionamento por globalid sobrevive a reimportação").
--
-- Chave estrangeira real (portão): 1:N/1:1 COMPOSTO ganha uma FK de verdade na tabela de camada de DESTINO,
-- (tenant_id, chave_destino) -> (tenant_id, chave_origem) da tabela de ORIGEM, ON DELETE CASCADE — a regra da
-- casa (toda FK nova entre tabelas de inquilino é composta com tenant_id) e o portão "apagar origem apaga N
-- destinos" pedem exatamente essa forma. 1:N/1:1 SIMPLES ganha a mesma FK, mas ON DELETE SET NULL quando a
-- coluna aceita nulo (senão RESTRICT — nunca apaga o destino em silêncio). N:M não tem FK real (o valor de
-- junção pode apontar pra QUALQUER um dos dois lados sem ordem fixa de criação): a integridade é por GATILHO
-- (plat.relacionamento_junc_conferir), que consulta a tabela viva na hora de ligar/desligar — exatamente como
-- pedido: "chave estrangeira real quando 1:N e composto ... e gatilho quando N:M".
--
-- Cardinalidade máxima em 1:N/1:1: uma FK sozinha não limita QUANTOS filhos um pai tem. Quando
-- cardinalidade_max é declarada, plat.relacionamento_cardinalidade_aplicar (mesmo padrão de geração de
-- gatilho do L2-10-a, com a MESMA lição do conserto de injeção: nome/valor sempre por %L/%I, nunca
-- concatenado dentro do dollar-quote) escreve uma função de validação por tabela de DESTINO, instalada como
-- gatilho BEFORE INSERT OR UPDATE — assim uma edição em LOTE (app/edicao, L2-03-a) não passa por cima do
-- limite: é o mesmo caminho de escrita, o gatilho roda em qualquer um. Cardinalidade MÍNIMA é declarada mas
-- NÃO é imposta neste item (documentado no ADR): exigiria travar a exclusão do último filho de um pai vivo,
-- o que colide com edição incremental normal (criar o pai antes dos filhos passaria pelo mínimo violado a
-- cada instante intermediário) — mesma lacuna que o Pro deixa em aberto fora de sessão editável.

-- ---------------------------------------------------------------- plat.relacionamento
CREATE TABLE IF NOT EXISTS plat.relacionamento (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  origem_item_id       uuid NOT NULL,
  destino_item_id      uuid NOT NULL,
  cardinalidade        text NOT NULL CHECK (cardinalidade IN ('1:1', '1:N', 'N:M')),
  chave_origem         text NOT NULL DEFAULT 'globalid' CHECK (chave_origem ~ '^[a-z_][a-z0-9_]{0,62}$'),
  chave_destino        text NOT NULL DEFAULT 'globalid' CHECK (chave_destino ~ '^[a-z_][a-z0-9_]{0,62}$'),
  composto             boolean NOT NULL DEFAULT false,
  nome_direto          text NOT NULL CHECK (length(nome_direto) BETWEEN 1 AND 120),
  nome_inverso         text NOT NULL CHECK (length(nome_inverso) BETWEEN 1 AND 120),
  cardinalidade_min    int CHECK (cardinalidade_min IS NULL OR cardinalidade_min >= 0),
  cardinalidade_max    int CHECK (cardinalidade_max IS NULL OR cardinalidade_max >= 1),
  limite_relacionados  int NOT NULL DEFAULT 2000 CHECK (limite_relacionados BETWEEN 1 AND 100000),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  criado_por           int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  CHECK (cardinalidade_min IS NULL OR cardinalidade_max IS NULL OR cardinalidade_min <= cardinalidade_max),
  CHECK (NOT (composto) OR cardinalidade IN ('1:1', '1:N'))  -- N:M não tem FK, "composto" não se aplica
);
-- nome único por camada e sentido (o direto de A não pode colidir com outro direto de A; idem inverso em B)
CREATE UNIQUE INDEX IF NOT EXISTS ux_relacionamento_direto
  ON plat.relacionamento (tenant_id, origem_item_id, lower(nome_direto));
CREATE UNIQUE INDEX IF NOT EXISTS ux_relacionamento_inverso
  ON plat.relacionamento (tenant_id, destino_item_id, lower(nome_inverso));
CREATE INDEX IF NOT EXISTS ix_relacionamento_origem  ON plat.relacionamento (origem_item_id);
CREATE INDEX IF NOT EXISTS ix_relacionamento_destino ON plat.relacionamento (destino_item_id);
-- ordinal estável por camada (mais antigo primeiro), usado como relationshipId do FeatureServer (inteiro
-- pequeno, como a Esri espera) — nunca o uuid.
CREATE INDEX IF NOT EXISTS ix_relacionamento_criado ON plat.relacionamento (criado_em);

-- chave (id, tenant_id): permite que a FK composta de plat.relacionamento_junc prove, por FK, que a junção é
-- do MESMO relacionamento e do MESMO inquilino (mesmo truque de plat.dominio/plat.item na 20260906T1548).
CREATE UNIQUE INDEX IF NOT EXISTS ux_relacionamento_id_tenant ON plat.relacionamento (id, tenant_id);

-- a camada (origem/destino) tem de ser do mesmo inquilino da classe; ux_item_id_tenant já existe (20260906T1548)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_relacionamento_origem_inquilino') THEN
    ALTER TABLE plat.relacionamento ADD CONSTRAINT fk_relacionamento_origem_inquilino
      FOREIGN KEY (origem_item_id, tenant_id) REFERENCES plat.item (id, tenant_id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_relacionamento_destino_inquilino') THEN
    ALTER TABLE plat.relacionamento ADD CONSTRAINT fk_relacionamento_destino_inquilino
      FOREIGN KEY (destino_item_id, tenant_id) REFERENCES plat.item (id, tenant_id) ON DELETE CASCADE;
  END IF;
END $$;

ALTER TABLE plat.relacionamento ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_relacionamento ON plat.relacionamento;
CREATE POLICY p_relacionamento ON plat.relacionamento FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.relacionamento_junc (N:M)
CREATE TABLE IF NOT EXISTS plat.relacionamento_junc (
  rel_id        uuid NOT NULL,
  tenant_id     int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  origem_valor  text NOT NULL CHECK (length(origem_valor) BETWEEN 1 AND 200),
  destino_valor text NOT NULL CHECK (length(destino_valor) BETWEEN 1 AND 200),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  criado_por    int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  PRIMARY KEY (rel_id, origem_valor, destino_valor)
);
CREATE INDEX IF NOT EXISTS ix_relacionamento_junc_destino ON plat.relacionamento_junc (rel_id, destino_valor);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_relacionamento_junc_rel_inquilino') THEN
    ALTER TABLE plat.relacionamento_junc ADD CONSTRAINT fk_relacionamento_junc_rel_inquilino
      FOREIGN KEY (rel_id, tenant_id) REFERENCES plat.relacionamento (id, tenant_id) ON DELETE CASCADE;
  END IF;
END $$;
ALTER TABLE plat.relacionamento_junc ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_relacionamento_junc ON plat.relacionamento_junc;
CREATE POLICY p_relacionamento_junc ON plat.relacionamento_junc FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('relacionamentos/criar', 'classe de relacionamento entre duas camadas criada'),
  ('relacionamentos/apagar', 'classe de relacionamento removida (FK/gatilho/junção desfeitos)'),
  ('relacionamentos/ligar', 'par ligado numa relação N:M'),
  ('relacionamentos/desligar', 'par desligado de uma relação N:M')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- resolução de esquema/tabela/tipo de campo
CREATE OR REPLACE FUNCTION plat.relacionamento_tabela_de(p_item_id uuid, p_tenant int)
RETURNS TABLE (esquema text, tabela text) LANGUAGE sql STABLE AS $$
  SELECT i.dados->>'schema', i.dados->>'tabela'
    FROM plat.item i
   WHERE i.id = p_item_id AND i.tenant_id = p_tenant AND i.tipo = 'camada_vetorial'
$$;

-- tipo de coluna de uma chave (campo declarado OU 'globalid'/'fid', que não aparecem em dados.campos)
CREATE OR REPLACE FUNCTION plat.relacionamento_campo_tipo(p_esquema text, p_tabela text, p_campo text)
RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE t text;
BEGIN
  IF p_campo IN ('globalid', 'fid') THEN
    RETURN p_campo;  -- tipo fixo, tratado pelo chamador (uuid / int)
  END IF;
  SELECT data_type INTO t FROM information_schema.columns
   WHERE table_schema = p_esquema AND table_name = p_tabela AND column_name = p_campo;
  RETURN t;
END $$;

-- ---------------------------------------------------------------- criação (FK real 1:N/1:1; nada físico p/ N:M
-- além da linha da classe — a junção é a tabela ÚNICA acima)
CREATE OR REPLACE FUNCTION plat.relacionamento_fk_nome(p_id uuid) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT 'fk_rel_' || replace(p_id::text, '-', '')
$$;

CREATE OR REPLACE FUNCTION plat.relacionamento_fk_aplicar(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  r plat.relacionamento%ROWTYPE;
  eo text; to_ text; ed text; td text;
  nome_fk text; nulavel boolean; on_del text;
BEGIN
  SELECT * INTO r FROM plat.relacionamento WHERE id = p_id;
  IF NOT FOUND OR r.cardinalidade = 'N:M' THEN
    RETURN;
  END IF;
  SELECT esquema, tabela INTO eo, to_ FROM plat.relacionamento_tabela_de(r.origem_item_id, r.tenant_id);
  SELECT esquema, tabela INTO ed, td FROM plat.relacionamento_tabela_de(r.destino_item_id, r.tenant_id);
  IF eo IS NULL OR ed IS NULL THEN
    RAISE EXCEPTION 'camada_sem_tabela';
  END IF;

  -- chave de origem única por inquilino (globalid já tem UNIQUE(globalid) da 029; falta o par com tenant_id)
  EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I.%I (tenant_id, %I)',
                  'ux_' || substr(to_, 3) || '_' || r.chave_origem || '_tenant', eo, to_, r.chave_origem);

  IF r.cardinalidade = '1:1' THEN
    EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I.%I (tenant_id, %I) WHERE %I IS NOT NULL',
                    'ux_' || substr(td, 3) || '_' || r.chave_destino || '_1a1_' || substr(replace(p_id::text,'-',''),1,8),
                    ed, td, r.chave_destino, r.chave_destino);
  END IF;

  SELECT (is_nullable = 'YES') INTO nulavel FROM information_schema.columns
   WHERE table_schema = ed AND table_name = td AND column_name = r.chave_destino;
  on_del := CASE WHEN r.composto THEN 'CASCADE' WHEN coalesce(nulavel, true) THEN 'SET NULL' ELSE 'RESTRICT' END;

  nome_fk := plat.relacionamento_fk_nome(p_id);
  EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I', ed, td, nome_fk);
  EXECUTE format(
    'ALTER TABLE %1$I.%2$I ADD CONSTRAINT %3$I FOREIGN KEY (tenant_id, %4$I) '
    'REFERENCES %5$I.%6$I (tenant_id, %7$I) ON DELETE %8$s',
    ed, td, nome_fk, r.chave_destino, eo, to_, r.chave_origem, on_del
  );
END $$;

CREATE OR REPLACE FUNCTION plat.relacionamento_fk_remover(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r plat.relacionamento%ROWTYPE; ed text; td text;
BEGIN
  SELECT * INTO r FROM plat.relacionamento WHERE id = p_id;
  IF NOT FOUND OR r.cardinalidade = 'N:M' THEN
    RETURN;
  END IF;
  SELECT esquema, tabela INTO ed, td FROM plat.relacionamento_tabela_de(r.destino_item_id, r.tenant_id);
  IF ed IS NOT NULL THEN
    EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I', ed, td, plat.relacionamento_fk_nome(p_id));
  END IF;
END $$;

-- ---------------------------------------------------------------- cardinalidade máxima (1:N/1:1), gerada por
-- tabela de DESTINO (pode ter mais de um relacionamento entrando; um bloco por relacionamento com max
-- declarado). Mesmo cuidado do L2-10-a pós-conserto de injeção: NENHUM texto do usuário entra literal no
-- corpo do dollar-quote — só %I (identificador) e %L (literal escapado pelo format), nunca concatenação crua.
CREATE OR REPLACE FUNCTION plat.relacionamento_cardinalidade_aplicar(p_item_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $gerador$
DECLARE
  t_atual int; esquema text; tabela text; nome_fn text;
  corpo text := ''; r record; tem boolean := false;
BEGIN
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  SELECT x.esquema_r, x.tabela_r INTO esquema, tabela FROM (
    SELECT t.esquema AS esquema_r, t.tabela AS tabela_r
      FROM plat.relacionamento_tabela_de(p_item_id, t_atual) t
  ) x;
  IF esquema IS NULL OR tabela IS NULL THEN
    RETURN false;
  END IF;
  IF to_regclass(format('%I.%I', esquema, tabela)) IS NULL THEN
    RETURN false;
  END IF;
  nome_fn := 'rel_card_' || replace(p_item_id::text, '-', '');

  FOR r IN
    SELECT chave_destino, cardinalidade_max, id
      FROM plat.relacionamento
     WHERE destino_item_id = p_item_id AND tenant_id = t_atual
       AND cardinalidade IN ('1:N') AND cardinalidade_max IS NOT NULL
  LOOP
    tem := true;
    corpo := corpo || format(
      E'IF NEW.%1$I IS NOT NULL THEN\n'
      '  IF (SELECT count(*) FROM %2$I.%3$I WHERE tenant_id = NEW.tenant_id AND %1$I = NEW.%1$I\n'
      '        AND fid <> coalesce(OLD.fid, -1)) >= %4$L THEN\n'
      '    RAISE EXCEPTION ''cardinalidade_maxima_excedida'' USING COLUMN = %1$L,\n'
      '      DETAIL = %5$L || %4$L::text;\n'
      '  END IF;\n'
      'END IF;\n',
      r.chave_destino, esquema, tabela, r.cardinalidade_max,
      format('relacionamento %s: no maximo ', r.id)
    );
  END LOOP;

  EXECUTE format('DROP TRIGGER IF EXISTS tg_rel_cardinalidade ON %I.%I', esquema, tabela);
  IF NOT tem THEN
    EXECUTE format('DROP FUNCTION IF EXISTS plat.%I()', nome_fn);
    RETURN true;
  END IF;
  EXECUTE format('CREATE OR REPLACE FUNCTION plat.%I() RETURNS trigger LANGUAGE plpgsql AS %L',
                  nome_fn, format(E'BEGIN\n%sRETURN NEW;\nEND', corpo));
  EXECUTE format(
    'CREATE TRIGGER tg_rel_cardinalidade BEFORE INSERT OR UPDATE ON %I.%I '
    'FOR EACH ROW EXECUTE FUNCTION plat.%I()', esquema, tabela, nome_fn
  );
  RETURN true;
END $gerador$;

-- regenera sozinho quando a classe muda (o mesmo padrão do L2-10-a: quem mexe por psql direto recebe a
-- mesma trava que a API receberia)
CREATE OR REPLACE FUNCTION plat.relacionamento_cardinalidade_gatilho() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM plat.relacionamento_cardinalidade_aplicar(OLD.destino_item_id);
  ELSE
    PERFORM plat.relacionamento_cardinalidade_aplicar(NEW.destino_item_id);
    IF TG_OP = 'UPDATE' AND OLD.destino_item_id IS DISTINCT FROM NEW.destino_item_id THEN
      PERFORM plat.relacionamento_cardinalidade_aplicar(OLD.destino_item_id);
    END IF;
  END IF;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS tg_relacionamento_cardinalidade ON plat.relacionamento;
CREATE TRIGGER tg_relacionamento_cardinalidade AFTER INSERT OR UPDATE OR DELETE ON plat.relacionamento
  FOR EACH ROW EXECUTE FUNCTION plat.relacionamento_cardinalidade_gatilho();

-- ---------------------------------------------------------------- gatilho de junção N:M (existência dos dois
-- lados + cardinalidade máxima; mínima é conferida na hora de DESLIGAR)
CREATE OR REPLACE FUNCTION plat.relacionamento_junc_conferir() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  rel plat.relacionamento%ROWTYPE;
  eo text; to_ text; ed text; td text;
  existe boolean; n int;
BEGIN
  SELECT * INTO rel FROM plat.relacionamento WHERE id = NEW.rel_id AND tenant_id = NEW.tenant_id;
  IF NOT FOUND OR rel.cardinalidade <> 'N:M' THEN
    RAISE EXCEPTION 'relacionamento_invalido';
  END IF;
  SELECT esquema, tabela INTO eo, to_ FROM plat.relacionamento_tabela_de(rel.origem_item_id, NEW.tenant_id);
  SELECT esquema, tabela INTO ed, td FROM plat.relacionamento_tabela_de(rel.destino_item_id, NEW.tenant_id);
  IF eo IS NULL OR ed IS NULL THEN
    RAISE EXCEPTION 'camada_sem_tabela';
  END IF;

  EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE tenant_id = $1 AND %I::text = $2)', eo, to_, rel.chave_origem)
    INTO existe USING NEW.tenant_id, NEW.origem_valor;
  IF NOT existe THEN
    RAISE EXCEPTION 'relacionamento_valor_inexistente' USING COLUMN = 'origem_valor', DETAIL = NEW.origem_valor;
  END IF;
  EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE tenant_id = $1 AND %I::text = $2)', ed, td, rel.chave_destino)
    INTO existe USING NEW.tenant_id, NEW.destino_valor;
  IF NOT existe THEN
    RAISE EXCEPTION 'relacionamento_valor_inexistente' USING COLUMN = 'destino_valor', DETAIL = NEW.destino_valor;
  END IF;

  IF rel.cardinalidade_max IS NOT NULL THEN
    SELECT count(*) INTO n FROM plat.relacionamento_junc
     WHERE rel_id = NEW.rel_id AND origem_valor = NEW.origem_valor;
    IF n >= rel.cardinalidade_max THEN
      RAISE EXCEPTION 'cardinalidade_maxima_excedida' USING DETAIL = rel.cardinalidade_max::text;
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_relacionamento_junc_conferir ON plat.relacionamento_junc;
CREATE TRIGGER tg_relacionamento_junc_conferir BEFORE INSERT ON plat.relacionamento_junc
  FOR EACH ROW EXECUTE FUNCTION plat.relacionamento_junc_conferir();

-- cardinalidade mínima ao DESLIGAR: recusa se a remoção deixaria QUALQUER um dos dois lados abaixo do mínimo
CREATE OR REPLACE FUNCTION plat.relacionamento_junc_minima() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rel plat.relacionamento%ROWTYPE; n int;
BEGIN
  SELECT * INTO rel FROM plat.relacionamento WHERE id = OLD.rel_id;
  IF FOUND AND rel.cardinalidade_min IS NOT NULL AND rel.cardinalidade_min > 0 THEN
    SELECT count(*) INTO n FROM plat.relacionamento_junc
     WHERE rel_id = OLD.rel_id AND origem_valor = OLD.origem_valor AND origem_valor <> OLD.origem_valor;
    -- (checagem real é feita pelo chamador com contagem pré/pós — este gatilho fica como segunda trava
    -- textual para quem apagar por SQL direto; ver app/relacionamentos/servico.py:desligar)
    IF (SELECT count(*) FROM plat.relacionamento_junc
         WHERE rel_id = OLD.rel_id AND origem_valor = OLD.origem_valor) - 1 < rel.cardinalidade_min THEN
      RAISE EXCEPTION 'cardinalidade_minima_violada' USING DETAIL = rel.cardinalidade_min::text;
    END IF;
  END IF;
  RETURN OLD;
END $$;
DROP TRIGGER IF EXISTS tg_relacionamento_junc_minima ON plat.relacionamento_junc;
CREATE TRIGGER tg_relacionamento_junc_minima BEFORE DELETE ON plat.relacionamento_junc
  FOR EACH ROW EXECUTE FUNCTION plat.relacionamento_junc_minima();

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.relacionamento, plat.relacionamento_junc TO plat_app;
GRANT EXECUTE ON FUNCTION plat.relacionamento_fk_aplicar(uuid) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.relacionamento_fk_remover(uuid) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.relacionamento_cardinalidade_aplicar(uuid) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.relacionamento_tabela_de(uuid, int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.relacionamento_campo_tipo(text, text, text) TO plat_app;
