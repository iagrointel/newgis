-- 20260906T1548_dominios_subtipos: domínios de atributo e subtipos como objetos do inquilino
-- (item L2-10-a-dominios-subtipos). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- O que entra:
--   plat.dominio        — o domínio em si (codificado com lista de valores, ou intervalo com mínimo/máximo).
--                         `valores` jsonb é a forma declarada e a que a API devolve.
--   plat.dominio_valor  — índice de pertinência DERIVADO de plat.dominio.valores, mantido pelo gatilho
--                         plat.dominio_sincronizar. Existe por desempenho: a validação por linha vira uma
--                         sondagem de índice (PK) em vez de varrer um array jsonb de milhares de códigos.
--                         Nunca é escrito por fora; quem edita escreve em plat.dominio.valores.
--   plat.dominio_campo  — ligação campo -> domínio POR CAMADA e por subtipo (subtipo_codigo NULL = padrão
--                         da camada; linha com subtipo_codigo preenchido sobrepõe a padrão naquele subtipo).
--   plat.camada_subtipo — o campo inteiro designado como subtipo da camada + a lista {codigo, nome, padroes}.
--
-- Código de erro: todo RAISE daqui sai com o errcode PADRÃO (P0001/raise_exception) e o CÓDIGO CURTO na
-- mensagem primária, que é o contrato que `app/auth/comum.erro_do_banco` lê para virar status HTTP. Com
-- ERRCODE='check_violation' o psycopg2 devolveria CheckViolation e o tradutor cairia no 422 genérico,
-- perdendo a contagem do 'valor_em_uso' e o nome do campo.
--
-- Aplicação no banco: gatilho genérico plat.feicao_validar_dominio() por linha, instalado/removido por
-- plat.camada_dominios_aplicar() — não CHECK, porque (a) mudar a lista de valores não pode exigir ALTER
-- TABLE e (b) a mensagem precisa citar o campo e o valor recusado (RAISE ... USING COLUMN).
--
-- Remoção de valor em uso: plat.dominio_uso_contar() conta, com SQL dinâmico, quantas feições usam o código
-- em todas as camadas ligadas; o gatilho de plat.dominio recusa a remoção com 'valor_em_uso' e o DETAIL traz
-- o código e a contagem — a API traduz para 409 (app/dominios/rotas.py).

-- ---------------------------------------------------------------- plat.dominio
CREATE TABLE IF NOT EXISTS plat.dominio (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  nome        text NOT NULL CHECK (length(nome) BETWEEN 1 AND 120),
  tipo        text NOT NULL CHECK (tipo IN ('codificado', 'intervalo')),
  tipo_campo  text NOT NULL CHECK (tipo_campo IN ('text', 'smallint', 'integer', 'bigint',
                                                  'double precision', 'real', 'numeric', 'date')),
  valores     jsonb NOT NULL DEFAULT '[]'::jsonb,
  descricao   text,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  criado_por  int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_por int REFERENCES plat.usuario(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dominio_nome ON plat.dominio (tenant_id, lower(nome));
-- chave composta: deixa a ligação em plat.dominio_campo provar, por FK, que o domínio é do MESMO inquilino
CREATE UNIQUE INDEX IF NOT EXISTS ux_dominio_id_tenant ON plat.dominio (id, tenant_id);
ALTER TABLE plat.dominio ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_dominio ON plat.dominio;
CREATE POLICY p_dominio ON plat.dominio FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.dominio_valor (derivado)
CREATE TABLE IF NOT EXISTS plat.dominio_valor (
  dominio_id uuid NOT NULL REFERENCES plat.dominio(id) ON DELETE CASCADE,
  tenant_id  int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  codigo     text NOT NULL,
  descricao  text NOT NULL,
  ordem      int  NOT NULL DEFAULT 0,
  ativo      boolean NOT NULL DEFAULT true,
  PRIMARY KEY (dominio_id, codigo)
);
ALTER TABLE plat.dominio_valor ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_dominio_valor ON plat.dominio_valor;
CREATE POLICY p_dominio_valor ON plat.dominio_valor FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.camada_subtipo
CREATE TABLE IF NOT EXISTS plat.camada_subtipo (
  item_id   uuid PRIMARY KEY REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  campo     text NOT NULL CHECK (campo ~ '^[a-z_][a-z0-9_]{0,62}$'),
  valores   jsonb NOT NULL DEFAULT '[]'::jsonb,
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE plat.camada_subtipo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_camada_subtipo ON plat.camada_subtipo;
CREATE POLICY p_camada_subtipo ON plat.camada_subtipo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.dominio_campo
CREATE TABLE IF NOT EXISTS plat.dominio_campo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  item_id       uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  campo         text NOT NULL CHECK (campo ~ '^[a-z_][a-z0-9_]{0,62}$'),
  subtipo_codigo int,
  dominio_id    uuid NOT NULL REFERENCES plat.dominio(id) ON DELETE RESTRICT,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_dominio_campo_mesmo_inquilino
    FOREIGN KEY (dominio_id, tenant_id) REFERENCES plat.dominio (id, tenant_id) ON DELETE RESTRICT
);
-- um domínio por (camada, campo, subtipo); a linha sem subtipo é a padrão da camada
CREATE UNIQUE INDEX IF NOT EXISTS ux_dominio_campo
  ON plat.dominio_campo (item_id, campo, coalesce(subtipo_codigo, -2147483648));
CREATE INDEX IF NOT EXISTS ix_dominio_campo_dominio ON plat.dominio_campo (dominio_id);
ALTER TABLE plat.dominio_campo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_dominio_campo ON plat.dominio_campo;
CREATE POLICY p_dominio_campo ON plat.dominio_campo FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- a camada tem de ser do mesmo inquilino da ligação (plat.item não tem chave (id, tenant_id) declarada;
-- o índice único abaixo cria a chave e a FK composta passa a valer também para o item)
CREATE UNIQUE INDEX IF NOT EXISTS ux_item_id_tenant ON plat.item (id, tenant_id);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_dominio_campo_item_inquilino') THEN
    ALTER TABLE plat.dominio_campo ADD CONSTRAINT fk_dominio_campo_item_inquilino
      FOREIGN KEY (item_id, tenant_id) REFERENCES plat.item (id, tenant_id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_camada_subtipo_item_inquilino') THEN
    ALTER TABLE plat.camada_subtipo ADD CONSTRAINT fk_camada_subtipo_item_inquilino
      FOREIGN KEY (item_id, tenant_id) REFERENCES plat.item (id, tenant_id) ON DELETE CASCADE;
  END IF;
END $$;

-- ---------------------------------------------------------------- forma dos valores + sincronia do derivado
-- Duas funções, não uma: a conferência de FORMA é BEFORE (precisa recusar antes de gravar e ainda ajusta
-- atualizado_em) e a sincronia do derivado é AFTER (plat.dominio_valor tem chave estrangeira para
-- plat.dominio: num BEFORE INSERT a linha do domínio ainda não existe e o INSERT do derivado quebra).
-- Limite de códigos: um domínio codificado é lista de escolha de formulário, não tabela de dados. 2.000 é o
-- teto (o Pro trava a edição bem antes disso); acima vira erro no banco e 422 na API.
CREATE OR REPLACE FUNCTION plat.dominio_conferir() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v jsonb; n int; cod text;
BEGIN
  IF NEW.tipo = 'codificado' THEN
    IF jsonb_typeof(NEW.valores) <> 'array' THEN
      RAISE EXCEPTION 'dominio_valores_invalidos' USING
        DETAIL = 'domínio codificado espera uma lista de valores';
    END IF;
    n := jsonb_array_length(NEW.valores);
    IF n = 0 THEN
      RAISE EXCEPTION 'dominio_sem_valores' USING
        DETAIL = 'domínio codificado precisa de pelo menos um valor';
    END IF;
    IF n > 2000 THEN
      RAISE EXCEPTION 'dominio_valores_demais' USING
        DETAIL = n::text;
    END IF;
    FOR v IN SELECT jsonb_array_elements(NEW.valores) LOOP
      IF jsonb_typeof(v) <> 'object' OR v->'codigo' IS NULL OR v->'descricao' IS NULL THEN
        RAISE EXCEPTION 'dominio_valor_incompleto' USING
          DETAIL = 'cada valor precisa de codigo e descricao';
      END IF;
    END LOOP;
    -- código duplicado na mesma lista: recusado aqui (a PK de plat.dominio_valor também recusaria, mas com
    -- mensagem de banco em inglês e sem dizer qual código)
    SELECT x.codigo INTO cod FROM (
      SELECT e->>'codigo' AS codigo FROM jsonb_array_elements(NEW.valores) e
    ) x GROUP BY x.codigo HAVING count(*) > 1 LIMIT 1;
    IF cod IS NOT NULL THEN
      RAISE EXCEPTION 'dominio_codigo_duplicado' USING DETAIL = cod;
    END IF;
  ELSE
    -- fronteira declarada: intervalo só sobre tipo numérico. Intervalo de data existe no Pro; aqui não foi
    -- construído nem medido, então o banco recusa em vez de deixar passar meio funcionando.
    IF NEW.tipo_campo NOT IN ('smallint', 'integer', 'bigint', 'double precision', 'real', 'numeric') THEN
      RAISE EXCEPTION 'dominio_intervalo_tipo' USING
        DETAIL = NEW.tipo_campo;
    END IF;
    IF jsonb_typeof(NEW.valores) <> 'object'
       OR jsonb_typeof(NEW.valores->'min') <> 'number' OR jsonb_typeof(NEW.valores->'max') <> 'number' THEN
      RAISE EXCEPTION 'dominio_intervalo_invalido' USING
        DETAIL = 'domínio de intervalo espera {"min": número, "max": número}';
    END IF;
    IF (NEW.valores->>'min')::numeric > (NEW.valores->>'max')::numeric THEN
      RAISE EXCEPTION 'dominio_intervalo_invertido' USING
        DETAIL = 'o mínimo é maior que o máximo';
    END IF;
  END IF;

  NEW.atualizado_em := now();
  RETURN NEW;
END $$;

-- AFTER: recusa remover valor em uso (com a contagem) e refaz o índice de pertinência derivado.
CREATE OR REPLACE FUNCTION plat.dominio_sincronizar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE usados bigint; cod text;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.tipo = 'codificado' THEN
    FOR cod IN
      SELECT e->>'codigo' FROM jsonb_array_elements(OLD.valores) e
      EXCEPT
      SELECT e->>'codigo' FROM jsonb_array_elements(
        CASE WHEN NEW.tipo = 'codificado' THEN NEW.valores ELSE '[]'::jsonb END) e
    LOOP
      usados := plat.dominio_uso_contar(NEW.id, cod);
      IF usados > 0 THEN
        RAISE EXCEPTION 'valor_em_uso' USING DETAIL = cod || '|' || usados::text;
      END IF;
    END LOOP;
  END IF;

  DELETE FROM plat.dominio_valor WHERE dominio_id = NEW.id;
  IF NEW.tipo = 'codificado' THEN
    INSERT INTO plat.dominio_valor (dominio_id, tenant_id, codigo, descricao, ordem, ativo)
    SELECT NEW.id, NEW.tenant_id, e->>'codigo', e->>'descricao',
           coalesce((e->>'ordem')::int, (ord - 1)::int), coalesce((e->>'ativo')::boolean, true)
      FROM jsonb_array_elements(NEW.valores) WITH ORDINALITY AS t(e, ord);
  END IF;
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS tg_dominio_conferir ON plat.dominio;
CREATE TRIGGER tg_dominio_conferir BEFORE INSERT OR UPDATE ON plat.dominio
  FOR EACH ROW EXECUTE FUNCTION plat.dominio_conferir();
DROP TRIGGER IF EXISTS tg_dominio_sincronizar ON plat.dominio;
CREATE TRIGGER tg_dominio_sincronizar AFTER INSERT OR UPDATE ON plat.dominio
  FOR EACH ROW EXECUTE FUNCTION plat.dominio_sincronizar();

-- ---------------------------------------------------------------- contagem de uso de um código
-- SECURITY DEFINER porque precisa ler o catálogo e as tabelas d_<slug>.c_<hex> de dentro da transação de
-- quem edita o domínio; o filtro por inquilino é explícito (tenant_atual), nunca herdado da RLS suspensa.
CREATE OR REPLACE FUNCTION plat.dominio_uso_contar(p_dominio_id uuid, p_codigo text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; r record; total bigint := 0; parcial bigint;
BEGIN
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  FOR r IN
    SELECT dc.campo, i.dados->>'schema' AS esquema, i.dados->>'tabela' AS tabela
      FROM plat.dominio_campo dc
      JOIN plat.item i ON i.id = dc.item_id
     WHERE dc.dominio_id = p_dominio_id AND dc.tenant_id = t_atual AND i.tenant_id = t_atual
       AND i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
  LOOP
    CONTINUE WHEN r.esquema IS NULL OR r.tabela IS NULL;
    CONTINUE WHEN r.esquema !~ '^[a-z][a-z0-9_]{1,62}$' OR r.tabela !~ '^[a-z][a-z0-9_]{1,62}$';
    CONTINUE WHEN to_regclass(format('%I.%I', r.esquema, r.tabela)) IS NULL;
    CONTINUE WHEN NOT EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = r.esquema AND table_name = r.tabela AND column_name = r.campo);
    EXECUTE format('SELECT count(*) FROM %I.%I WHERE tenant_id = $1 AND %I::text = $2',
                   r.esquema, r.tabela, r.campo)
      INTO parcial USING t_atual, p_codigo;
    total := total + coalesce(parcial, 0);
  END LOOP;
  RETURN total;
END $$;

-- ---------------------------------------------------------------- gatilho genérico de validação por feição
-- Instalado com o item_id da camada como argumento (TG_ARGV[0]). Lê as ligações a cada linha: uma sondagem
-- de índice em plat.dominio_campo e outra na PK de plat.dominio_valor — é o que segura o custo do gatilho.
CREATE OR REPLACE FUNCTION plat.feicao_validar_dominio() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_item uuid := TG_ARGV[0]::uuid;
  j jsonb := to_jsonb(NEW);
  v_campo_sub text; v_sub text; v_sub_num int; r record; texto text; num numeric;
BEGIN
  SELECT campo INTO v_campo_sub FROM plat.camada_subtipo WHERE item_id = v_item;
  IF v_campo_sub IS NOT NULL THEN
    v_sub := j->>v_campo_sub;
    BEGIN
      v_sub_num := v_sub::int;
    EXCEPTION WHEN others THEN
      v_sub_num := NULL;
    END;
    IF v_sub IS NOT NULL AND v_sub_num IS NULL THEN
      RAISE EXCEPTION 'subtipo_invalido' USING
        COLUMN = v_campo_sub,
        DETAIL = format('campo "%s": o subtipo %L não é um código inteiro', v_campo_sub, v_sub);
    END IF;
    IF v_sub_num IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM plat.camada_subtipo s, jsonb_array_elements(s.valores) e
          WHERE s.item_id = v_item AND (e->>'codigo')::int = v_sub_num) THEN
      RAISE EXCEPTION 'subtipo_invalido' USING
        COLUMN = v_campo_sub,
        DETAIL = format('campo "%s": o subtipo %L não está na lista de subtipos da camada', v_campo_sub, v_sub);
    END IF;
  END IF;

  FOR r IN
    SELECT DISTINCT ON (dc.campo) dc.campo, d.id AS dominio_id, d.nome, d.tipo, d.valores
      FROM plat.dominio_campo dc
      JOIN plat.dominio d ON d.id = dc.dominio_id
     WHERE dc.item_id = v_item
       AND (dc.subtipo_codigo IS NULL OR dc.subtipo_codigo = v_sub_num)
     ORDER BY dc.campo, (dc.subtipo_codigo IS NOT NULL) DESC
  LOOP
    texto := j->>r.campo;
    CONTINUE WHEN texto IS NULL;                       -- domínio não torna o campo obrigatório
    IF r.tipo = 'codificado' THEN
      IF NOT EXISTS (SELECT 1 FROM plat.dominio_valor dv
                      WHERE dv.dominio_id = r.dominio_id AND dv.codigo = texto) THEN
        RAISE EXCEPTION 'valor_fora_do_dominio' USING
          COLUMN = r.campo,
          DETAIL = format('campo "%s": o valor %L não pertence ao domínio "%s"', r.campo, texto, r.nome);
      END IF;
    ELSE
      BEGIN
        num := texto::numeric;
      EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'valor_fora_do_dominio' USING
          COLUMN = r.campo,
          DETAIL = format('campo "%s": o valor %L não é numérico e o domínio "%s" é de intervalo',
                          r.campo, texto, r.nome);
      END;
      IF num < (r.valores->>'min')::numeric OR num > (r.valores->>'max')::numeric THEN
        RAISE EXCEPTION 'valor_fora_do_dominio' USING
          COLUMN = r.campo,
          DETAIL = format('campo "%s": o valor %s está fora do intervalo %s a %s do domínio "%s"',
                          r.campo, texto, r.valores->>'min', r.valores->>'max', r.nome);
      END IF;
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------- instalar/remover o gatilho na tabela
-- SECURITY DEFINER: plat_app não tem privilégio de CREATE TRIGGER na tabela de camada (mesmo motivo de
-- plat.camada_preparar na 029). O gatilho só existe enquanto a camada tem ligação ou subtipo — camada sem
-- domínio nenhum não paga nada por linha.
CREATE OR REPLACE FUNCTION plat.camada_dominios_aplicar(p_item_id uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_atual int; esquema text; tabela text; precisa boolean;
BEGIN
  t_atual := plat.tenant_atual();
  IF t_atual IS NULL THEN
    RAISE EXCEPTION 'sem_tenant_no_contexto';
  END IF;
  SELECT i.dados->>'schema', i.dados->>'tabela' INTO esquema, tabela
    FROM plat.item i
   WHERE i.id = p_item_id AND i.tenant_id = t_atual AND i.tipo = 'camada_vetorial';
  IF esquema IS NULL OR tabela IS NULL THEN
    RETURN false;
  END IF;
  IF esquema !~ '^[a-z][a-z0-9_]{1,62}$' OR tabela !~ '^[a-z][a-z0-9_]{1,62}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  IF to_regclass(format('%I.%I', esquema, tabela)) IS NULL THEN
    RETURN false;
  END IF;
  precisa := EXISTS (SELECT 1 FROM plat.dominio_campo WHERE item_id = p_item_id AND tenant_id = t_atual)
          OR EXISTS (SELECT 1 FROM plat.camada_subtipo WHERE item_id = p_item_id AND tenant_id = t_atual);
  EXECUTE format('DROP TRIGGER IF EXISTS tg_dominio ON %I.%I', esquema, tabela);
  IF precisa THEN
    EXECUTE format('CREATE TRIGGER tg_dominio BEFORE INSERT OR UPDATE ON %I.%I '
                   'FOR EACH ROW EXECUTE FUNCTION plat.feicao_validar_dominio(%L)',
                   esquema, tabela, p_item_id::text);
  END IF;
  RETURN precisa;
END $$;

-- ---------------------------------------------------------------- privilégios
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.dominio, plat.dominio_valor, plat.dominio_campo,
      plat.camada_subtipo TO plat_app;
GRANT SELECT ON plat.dominio, plat.dominio_valor, plat.dominio_campo, plat.camada_subtipo TO plat_leitor;
GRANT EXECUTE ON FUNCTION plat.dominio_uso_contar(uuid, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.camada_dominios_aplicar(uuid) TO plat_app;

-- ---------------------------------------------------------------- eventos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('dominios/criar',    'domínio de atributo criado (L2-10-a)'),
  ('dominios/editar',   'domínio de atributo alterado (L2-10-a)'),
  ('dominios/apagar',   'domínio de atributo apagado (L2-10-a)'),
  ('dominios/ligar',    'domínio ligado a um campo de camada (L2-10-a)'),
  ('dominios/desligar', 'domínio desligado de um campo de camada (L2-10-a)'),
  ('dominios/importar', 'domínios importados de um serviço/geodatabase externo (L2-10-a)'),
  ('subtipos/definir',  'subtipos da camada definidos ou alterados (L2-10-a)')
ON CONFLICT (nome) DO NOTHING;
