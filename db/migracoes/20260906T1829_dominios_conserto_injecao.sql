-- 20260906T1829_dominios_conserto_injecao: conserto de segurança do item L2-10-a-dominios-subtipos
-- (achado do adversário, handoffs/T3/ataque-L2-hoje-ADVERSARIO.md). Idempotente. Sem BEGIN/COMMIT.
-- depende: 20260906T1620_dominios_gatilho_gerado.sql
--
-- O ACHADO. plat.camada_dominios_aplicar gera o corpo da função de validação e o embute num
-- CREATE FUNCTION delimitado por um dollar-tag FIXO ($corpo_gerado$). plat.dominio_bloco_sql escrevia o
-- NOME do domínio, texto do usuário, verbatim dentro desse corpo (protegido só por %L contra aspas e
-- ponto e vírgula — nunca contra o próprio delimitador). Um nome contendo a string "$corpo_gerado$" fecha
-- o corpo no meio e o resto vira SQL solto, executado como postgres (dono da função). O CHECK do banco só
-- limitava comprimento; só a API barrava "$" — e a própria migração 20260906T1620 declara que a API não é
-- a guarda (o gatilho AFTER regenera sozinho a partir de escrita direta por psql).
--
-- O CONSERTO, nas duas camadas:
--   1. plat.dominio_bloco_sql PARA de escrever o nome do domínio como texto literal no corpo gerado. A
--      mensagem de erro busca o nome em tempo de execução por uma sub-consulta em plat.dominio, chaveada
--      pelo id do domínio — que é sempre um uuid (nunca texto arbitrário do usuário). Não existe mais
--      texto de usuário dentro de $corpo_gerado$...$corpo_gerado$; o vetor fecha na raiz.
--   2. plat.camada_dominios_aplicar ganha uma conferência defensiva: se o corpo montado contiver a string
--      do delimitador (não deveria, depois de 1), a função recusa em vez de gerar SQL quebrado.
--   3. CHECK em plat.dominio.nome espelhando o padrão que a API já usa (NOME_PADRAO em
--      app/dominios/modelos.py: letras, dígitos, espaço, ponto, hífen, sublinhado) — assim a alteração por
--      psql também é recusada, com uma mensagem em português vinda do gatilho BEFORE que já existe
--      (plat.dominio_conferir), antes mesmo de o banco avaliar o CHECK.

-- ---------------------------------------------------------------- 1. gatilho BEFORE recusa nome perigoso
-- (mesmo padrão da API: app/dominios/modelos.py NOME_PADRAO = r"^[A-Za-z_][A-Za-z0-9_ .\-]{0,119}$")
CREATE OR REPLACE FUNCTION plat.dominio_conferir() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v jsonb; n int; cod text;
BEGIN
  IF NEW.nome !~ '^[A-Za-z_][A-Za-z0-9_ .\-]{0,119}$' THEN
    RAISE EXCEPTION 'dominio_nome_invalido' USING
      DETAIL = 'o nome do domínio só pode ter letras, números, espaço, ponto, hífen ou sublinhado, '
               'começando por letra ou sublinhado (mesma regra da API — vale também por psql)';
  END IF;

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
    SELECT x.codigo INTO cod FROM (
      SELECT e->>'codigo' AS codigo FROM jsonb_array_elements(NEW.valores) e
    ) x GROUP BY x.codigo HAVING count(*) > 1 LIMIT 1;
    IF cod IS NOT NULL THEN
      RAISE EXCEPTION 'dominio_codigo_duplicado' USING DETAIL = cod;
    END IF;
  ELSE
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

-- ---------------------------------------------------------------- CHECK de banco (retaguarda do trigger)
ALTER TABLE plat.dominio DROP CONSTRAINT IF EXISTS ck_dominio_nome_seguro;
ALTER TABLE plat.dominio ADD CONSTRAINT ck_dominio_nome_seguro
  CHECK (nome ~ '^[A-Za-z_][A-Za-z0-9_ .\-]{0,119}$');

-- ---------------------------------------------------------------- 2. o nome nunca mais vira texto no corpo
-- p_nome fica na assinatura só por compatibilidade com quem chama (não muda o contrato da função); o corpo
-- gerado busca o nome do domínio em tempo de execução pelo id, que é sempre um uuid seguro.
CREATE OR REPLACE FUNCTION plat.dominio_bloco_sql(p_campo text, p_dominio uuid, p_tipo text, p_nome text,
                                                  p_valores jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $bloco$
BEGIN
  IF p_tipo = 'codificado' THEN
    RETURN format(
      E'IF NEW.%1$I IS NOT NULL AND NOT EXISTS (SELECT 1 FROM plat.dominio_valor dv\n'
      '     WHERE dv.dominio_id = %2$L::uuid AND dv.codigo = NEW.%1$I::text) THEN\n'
      '  RAISE EXCEPTION ''valor_fora_do_dominio'' USING COLUMN = %3$L,\n'
      '    DETAIL = %4$L || NEW.%1$I::text || %5$L\n'
      '           || coalesce((SELECT nome FROM plat.dominio WHERE id = %2$L::uuid), ''?'') || %6$L;\n'
      'END IF;',
      p_campo, p_dominio, p_campo,
      format('campo "%s": o valor ''', p_campo),
      ''' não pertence ao domínio "',
      '"');
  END IF;
  RETURN format(
    E'IF NEW.%1$I IS NOT NULL AND (NEW.%1$I::numeric < %2$L::numeric\n'
    '     OR NEW.%1$I::numeric > %3$L::numeric) THEN\n'
    '  RAISE EXCEPTION ''valor_fora_do_dominio'' USING COLUMN = %4$L,\n'
    '    DETAIL = %5$L || NEW.%1$I::text || %6$L\n'
    '           || coalesce((SELECT nome FROM plat.dominio WHERE id = %7$L::uuid), ''?'') || %8$L;\n'
    'END IF;',
    p_campo, p_valores->>'min', p_valores->>'max', p_campo,
    format('campo "%s": o valor ', p_campo),
    format(' está fora do intervalo %s a %s do domínio "', p_valores->>'min', p_valores->>'max'),
    p_dominio, '"');
END $bloco$;

-- ---------------------------------------------------------------- 3. defesa em profundidade no gerador
-- Mesmo corpo não devendo mais conter o delimitador (item 2 fechou a raiz), o gerador recusa em vez de
-- montar um CREATE FUNCTION quebrado se, por qualquer via futura, o texto aparecer.
CREATE OR REPLACE FUNCTION plat.camada_dominios_aplicar(p_item_id uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $gerador$
DECLARE
  t_atual int; esquema text; tabela text; nome_fn text;
  campo_sub text; codigos int[]; corpo text := ''; trecho text;
  r record; d record; tem boolean := false;
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
  nome_fn := 'dominio_v_' || replace(p_item_id::text, '-', '');

  SELECT s.campo, array_agg((e->>'codigo')::int ORDER BY (e->>'codigo')::int)
    INTO campo_sub, codigos
    FROM plat.camada_subtipo s, jsonb_array_elements(s.valores) e
   WHERE s.item_id = p_item_id AND s.tenant_id = t_atual
   GROUP BY s.campo;
  IF campo_sub IS NOT NULL THEN
    tem := true;
    corpo := corpo || format(
      E'IF NEW.%1$I IS NOT NULL AND NOT (NEW.%1$I = ANY (%2$L::int[])) THEN\n'
      '  RAISE EXCEPTION ''subtipo_invalido'' USING COLUMN = %3$L,\n'
      '    DETAIL = %4$L || NEW.%1$I::text || %5$L;\n'
      'END IF;\n',
      campo_sub, codigos, campo_sub,
      format('campo "%s": o subtipo ', campo_sub), ' não está na lista de subtipos da camada');
  END IF;

  FOR r IN
    SELECT dc.campo FROM plat.dominio_campo dc
     WHERE dc.item_id = p_item_id AND dc.tenant_id = t_atual
     GROUP BY dc.campo ORDER BY dc.campo
  LOOP
    tem := true;
    IF campo_sub IS NOT NULL AND EXISTS (
         SELECT 1 FROM plat.dominio_campo WHERE item_id = p_item_id AND campo = r.campo
          AND subtipo_codigo IS NOT NULL) THEN
      trecho := format(E'CASE NEW.%I\n', campo_sub);
      FOR d IN
        SELECT dc.subtipo_codigo, dom.id, dom.tipo, dom.nome, dom.valores
          FROM plat.dominio_campo dc JOIN plat.dominio dom ON dom.id = dc.dominio_id
         WHERE dc.item_id = p_item_id AND dc.campo = r.campo AND dc.subtipo_codigo IS NOT NULL
         ORDER BY dc.subtipo_codigo
      LOOP
        trecho := trecho || format(E'WHEN %s THEN\n%s\n', d.subtipo_codigo,
                                   plat.dominio_bloco_sql(r.campo, d.id, d.tipo, d.nome, d.valores));
      END LOOP;
      SELECT dom.id, dom.tipo, dom.nome, dom.valores INTO d
        FROM plat.dominio_campo dc JOIN plat.dominio dom ON dom.id = dc.dominio_id
       WHERE dc.item_id = p_item_id AND dc.campo = r.campo AND dc.subtipo_codigo IS NULL;
      IF FOUND THEN
        trecho := trecho || format(E'ELSE\n%s\n',
                                   plat.dominio_bloco_sql(r.campo, d.id, d.tipo, d.nome, d.valores));
      ELSE
        trecho := trecho || E'ELSE NULL;\n';
      END IF;
      corpo := corpo || trecho || E'END CASE;\n';
    ELSE
      SELECT dom.id, dom.tipo, dom.nome, dom.valores INTO d
        FROM plat.dominio_campo dc JOIN plat.dominio dom ON dom.id = dc.dominio_id
       WHERE dc.item_id = p_item_id AND dc.campo = r.campo AND dc.subtipo_codigo IS NULL;
      IF FOUND THEN
        corpo := corpo || plat.dominio_bloco_sql(r.campo, d.id, d.tipo, d.nome, d.valores) || E'\n';
      END IF;
    END IF;
  END LOOP;

  EXECUTE format('DROP TRIGGER IF EXISTS tg_dominio ON %I.%I', esquema, tabela);
  IF NOT tem THEN
    EXECUTE format('DROP FUNCTION IF EXISTS plat.%I()', nome_fn);
    RETURN false;
  END IF;
  -- defesa em profundidade: o corpo não deve conter o delimitador nem em pedaço (nome não entra mais como
  -- texto — item 2 acima). Se algum dia entrar de outra forma, falha alto em vez de gerar SQL quebrado.
  IF corpo LIKE '%$corpo_gerado$%' OR corpo LIKE '%$$%' THEN
    RAISE EXCEPTION 'gerador_dominio_corpo_suspeito' USING
      DETAIL = 'o corpo gerado contém um delimitador de dollar-quote; recusado antes de compilar';
  END IF;
  EXECUTE format('CREATE OR REPLACE FUNCTION plat.%I() RETURNS trigger LANGUAGE plpgsql AS '
                 '$corpo_gerado$ BEGIN %s RETURN NEW; END $corpo_gerado$', nome_fn, corpo);
  EXECUTE format('CREATE TRIGGER tg_dominio BEFORE INSERT OR UPDATE ON %I.%I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.%I()', esquema, tabela, nome_fn);
  RETURN true;
END $gerador$;

-- ---------------------------------------------------------------- regenera o que já existia com o conserto
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT DISTINCT item_id, tenant_id FROM plat.dominio_campo
           UNION SELECT item_id, tenant_id FROM plat.camada_subtipo LOOP
    PERFORM set_config('plat.tenant_id', r.tenant_id::text, true);
    PERFORM plat.camada_dominios_aplicar(r.item_id);
  END LOOP;
END $$;
