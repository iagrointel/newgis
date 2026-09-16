-- 20260916T0937_revoke_public_dominio_v_auth_sessao: fecha EXECUTE para PUBLIC na 4ª e 5ª classe medidas da
-- mesma família (20260906T1615, 20260908T1031, 20260915T2250) — `CREATE FUNCTION` dá EXECUTE a PUBLIC por
-- padrão e nenhum dos dois pontos abaixo repetia o `REVOKE EXECUTE ... FROM PUBLIC` da casa.
--
-- MEDIDO 16/09/2026 (tests/api/catalogo/test_adversario_g2.py::test_g2_8_funcoes_do_plat_sem_execute_para_public,
-- reprodução isolada no laço f2fixcatalogo): 10 funções abertas.
--
--   1. `plat.auth_sessao(text, numeric)` — a migração 20260916T0135f2a_auth_sessao_suspenso_sem_apagar.sql
--      trocou o tipo de retorno (ganhou a coluna `tenant_ativo`), e Postgres recusa `CREATE OR REPLACE` quando
--      o tipo de retorno muda: o arquivo fez `DROP FUNCTION` + `CREATE FUNCTION`. O comentário do próprio
--      arquivo ("sem REVOKE específico dela nas migrações anteriores... fica igual") estava ERRADO: o que
--      fechava PUBLIC nela era só o `REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA plat FROM PUBLIC` de
--      003_identidade_acesso.sql — um comando de UMA VEZ SÓ sobre as funções que existiam NAQUELE momento, não
--      uma política permanente (confirmado nas três varreduras anteriores: mesmo com o `ALTER DEFAULT
--      PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` da fundação já em vigor, `CREATE FUNCTION` volta
--      a abrir PUBLIC — é o mesmo achado de 20260906T1615, medido de novo aqui). `DROP` apaga o GRANT nominal
--      junto com a função; a recriação nasce só com o padrão do Postgres (PUBLIC).
--   2. `plat.dominio_v_<item sem hífen>()` — gerada em TEMPO DE EXECUÇÃO por `plat.camada_dominios_aplicar`
--      (20260906T1620_dominios_gatilho_gerado.sql) toda vez que um domínio/subtipo é ligado a uma camada; a
--      função nunca tinha `REVOKE EXECUTE ... FROM PUBLIC` depois do `CREATE OR REPLACE FUNCTION` dinâmico —
--      ABERTA EM TODO INQUILINO QUE USA DOMÍNIO, não só nesta base. Sem consertar o GERADOR, a próxima vez que
--      alguém ligar um domínio a uma camada (em QUALQUER trilha ou em produção) abre outra função nova. Por
--      isso esta migração reescreve `plat.camada_dominios_aplicar` (CREATE OR REPLACE, mesma assinatura —
--      preserva os GRANTs da própria função) acrescentando o REVOKE que faltava logo depois do CREATE
--      dinâmico, e SÓ DEPOIS varre o que já existe nesta base.
--
-- Função de gatilho não perde nada com isso (o Postgres cobra EXECUTE dela em CREATE TRIGGER, não a cada
-- disparo — mesma nota das três varreduras anteriores). Idempotente; sem BEGIN/COMMIT.

-- ---------------------------------------------------------------- 1. conserto do gerador (raiz do achado 2)
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
  -- CONSERTO (achado G2-8, 16/09): a função dinâmica nascia com EXECUTE aberto para PUBLIC (padrão do
  -- Postgres em CREATE FUNCTION) e nunca era fechada. Gatilho não precisa de EXECUTE nominal nenhum (o
  -- Postgres cobra o privilégio em CREATE TRIGGER, não a cada disparo) — mesmo padrão das plat.tg_* da 011.
  EXECUTE format('REVOKE EXECUTE ON FUNCTION plat.%I() FROM PUBLIC, plat_app', nome_fn);
  EXECUTE format('CREATE TRIGGER tg_dominio BEFORE INSERT OR UPDATE ON %I.%I '
                 'FOR EACH ROW EXECUTE FUNCTION plat.%I()', esquema, tabela, nome_fn);
  RETURN true;
END $gerador$;

-- ---------------------------------------------------------------- 2. auth_sessao nominal + varredura genérica
GRANT EXECUTE ON FUNCTION plat.auth_sessao(text, numeric) TO plat_app;
REVOKE EXECUTE ON FUNCTION plat.auth_sessao(text, numeric) FROM PUBLIC;

DO $$
DECLARE f record;
BEGIN
  FOR f IN
    SELECT p.oid::regprocedure AS assinatura
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'plat'
      AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%'))
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f.assinatura);
  END LOOP;
END $$;
