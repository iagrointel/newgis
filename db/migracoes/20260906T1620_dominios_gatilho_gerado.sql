-- 20260906T1620_dominios_gatilho_gerado: o gatilho de domínio deixa de ser genérico e passa a ser GERADO por
-- camada (item L2-10-a-dominios-subtipos). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 20260906T1548_dominios_subtipos.sql
--
-- POR QUE. A primeira versão de plat.feicao_validar_dominio lia os campos da linha com `to_jsonb(NEW)`, que é
-- a única forma de um plpgsql genérico acessar um campo pelo nome. Medido em 10 mil inserções na mesma tabela
-- (tests/api/test_dominios_subtipos.py::test_custo_do_gatilho_em_10_mil_insercoes): 1,72 s sem gatilho contra
-- 3,11 s com, razão 1,80x — acima do teto de 1,5x do item. Um segundo teste isolou a causa: um gatilho que só
-- faz `to_jsonb(NEW)` e retorna já custa cerca de 129 us por linha, porque converte a linha INTEIRA, geometria
-- inclusive (a função de saída do tipo geometry roda a cada linha).
--
-- O QUE MUDA. plat.camada_dominios_aplicar passa a ESCREVER uma função de gatilho por camada,
-- `plat.dominio_v_<item sem hífen>`, com o nome de cada campo escrito no código (`NEW.uf`) — sem to_jsonb.
-- Fica embutido no código gerado só o que muda por DDL (nome do campo, id do domínio, lista de subtipos,
-- mínimo e máximo do intervalo); a LISTA DE CÓDIGOS continua sendo lida em plat.dominio_valor a cada linha
-- (uma sondagem de chave primária), porque ela pode ter milhares de itens.
--
-- E QUEM MANTÉM ISSO EM DIA. Não é a API: três gatilhos AFTER (em plat.dominio_campo, plat.camada_subtipo e
-- plat.dominio) chamam plat.camada_dominios_aplicar sozinhos. Quem alterar a ligação, o subtipo ou o domínio
-- por `psql` regenera a função do mesmo jeito. Regra que só a API mantivesse não seria regra.
--
-- A função genérica plat.feicao_validar_dominio da migração anterior fica no banco, sem uso, como registro do
-- caminho medido; nenhuma tabela a referencia depois desta migração.

-- ---------------------------------------------------------------- bloco de UM campo contra UM domínio
-- Devolve o texto plpgsql que confere o campo. O nome do domínio entra no código porque só aparece na
-- mensagem de erro; a lista de códigos, não (é lida do banco a cada linha).
CREATE OR REPLACE FUNCTION plat.dominio_bloco_sql(p_campo text, p_dominio uuid, p_tipo text, p_nome text,
                                                  p_valores jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $bloco$
BEGIN
  IF p_tipo = 'codificado' THEN
    RETURN format(
      E'IF NEW.%1$I IS NOT NULL AND NOT EXISTS (SELECT 1 FROM plat.dominio_valor dv\n'
      '     WHERE dv.dominio_id = %2$L::uuid AND dv.codigo = NEW.%1$I::text) THEN\n'
      '  RAISE EXCEPTION ''valor_fora_do_dominio'' USING COLUMN = %3$L,\n'
      '    DETAIL = %4$L || NEW.%1$I::text || %5$L;\n'
      'END IF;',
      p_campo, p_dominio, p_campo,
      format('campo "%s": o valor ''', p_campo),
      format(''' não pertence ao domínio "%s"', p_nome));
  END IF;
  RETURN format(
    E'IF NEW.%1$I IS NOT NULL AND (NEW.%1$I::numeric < %2$L::numeric\n'
    '     OR NEW.%1$I::numeric > %3$L::numeric) THEN\n'
    '  RAISE EXCEPTION ''valor_fora_do_dominio'' USING COLUMN = %4$L,\n'
    '    DETAIL = %5$L || NEW.%1$I::text || %6$L;\n'
    'END IF;',
    p_campo, p_valores->>'min', p_valores->>'max', p_campo,
    format('campo "%s": o valor ', p_campo),
    format(' está fora do intervalo %s a %s do domínio "%s"',
           p_valores->>'min', p_valores->>'max', p_nome));
END $bloco$;

-- ---------------------------------------------------------------- gerador
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

  -- subtipo da camada: campo designado + lista de códigos válidos
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

  -- um bloco por campo ligado; onde há override por subtipo, um CASE que despacha
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
        trecho := trecho || E'ELSE NULL;\n';   -- subtipo sem domínio próprio e sem padrão: nada a conferir
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
  EXECUTE format('CREATE OR REPLACE FUNCTION plat.%I() RETURNS trigger LANGUAGE plpgsql AS '
                 '$corpo_gerado$ BEGIN %s RETURN NEW; END $corpo_gerado$', nome_fn, corpo);
  EXECUTE format('CREATE TRIGGER tg_dominio BEFORE INSERT OR UPDATE ON %I.%I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.%I()', esquema, tabela, nome_fn);
  RETURN true;
END $gerador$;

-- ---------------------------------------------------------------- quem regenera, e sozinho
CREATE OR REPLACE FUNCTION plat.dominio_reaplicar_ligacao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM plat.camada_dominios_aplicar(coalesce(NEW.item_id, OLD.item_id));
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS tg_reaplicar ON plat.dominio_campo;
CREATE TRIGGER tg_reaplicar AFTER INSERT OR UPDATE OR DELETE ON plat.dominio_campo
  FOR EACH ROW EXECUTE FUNCTION plat.dominio_reaplicar_ligacao();

DROP TRIGGER IF EXISTS tg_reaplicar ON plat.camada_subtipo;
CREATE TRIGGER tg_reaplicar AFTER INSERT OR UPDATE OR DELETE ON plat.camada_subtipo
  FOR EACH ROW EXECUTE FUNCTION plat.dominio_reaplicar_ligacao();

-- alterar o domínio muda o que está embutido no código gerado (mínimo, máximo, nome na mensagem): regenera a
-- função de toda camada ligada. Substitui plat.dominio_sincronizar da migração anterior, acrescentando o laço.
CREATE OR REPLACE FUNCTION plat.dominio_sincronizar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE usados bigint; cod text; alvo uuid;
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

  IF TG_OP = 'UPDATE' THEN
    FOR alvo IN SELECT DISTINCT item_id FROM plat.dominio_campo WHERE dominio_id = NEW.id LOOP
      PERFORM plat.camada_dominios_aplicar(alvo);
    END LOOP;
  END IF;
  RETURN NULL;
END $$;

GRANT EXECUTE ON FUNCTION plat.dominio_bloco_sql(text, uuid, text, text, jsonb) TO plat_app;

-- ---------------------------------------------------------------- regenera o que já existia
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT DISTINCT item_id, tenant_id FROM plat.dominio_campo
           UNION SELECT item_id, tenant_id FROM plat.camada_subtipo LOOP
    PERFORM set_config('plat.tenant_id', r.tenant_id::text, true);
    PERFORM plat.camada_dominios_aplicar(r.item_id);
  END LOOP;
END $$;
