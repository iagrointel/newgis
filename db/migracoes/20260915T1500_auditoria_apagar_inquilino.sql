-- 20260915T1500_auditoria_apagar_inquilino: apagar um inquilino batia em `auditoria_imutavel`.
--
-- Defeito reproduzido pelo gerente: a fixture `inquilino_temporario` (tests/api/conftest.py:266-300) faz
-- DELETE /api/plataforma/inquilinos/{id} no teardown e recebia 409 `auditoria_imutavel` (10 arquivos de
-- teste usam a fixture; tests/api/conftest.py:360 também apaga inquilinos zt-* na varredura final). Causa:
-- `plat.tenant_apagar_interno` (20260910T2307_inquilino_apagar_schema.sql, depois reescrita por
-- 20260911T1440 para usar `plat.camada_schema_prefixo()`) apaga TODA tabela do schema com coluna
-- tenant_id, num loop dinâmico — inclusive `plat.auditoria`. Lá o gatilho `plat.tg_auditoria_imutavel()`
-- (20260906T1620_auditoria.sql) recusa qualquer DELETE que não traga a marca de expurgo + ser dono da
-- tabela, e a função de apagar inquilino não é dona nem liga aquela marca.
--
-- Correção SEM enfraquecer a imutabilidade no uso normal:
--   1. `plat.tg_auditoria_imutavel()` passa a aceitar DELETE (nunca UPDATE, nunca TRUNCATE — esse gatilho
--      nem dispara em TRUNCATE, que tem o seu próprio) quando a transação carrega a marca
--      `plat.apagando_inquilino = '1'`.
--   2. `plat.tenant_apagar_interno()` liga essa marca com `set_config(..., true)` — true = local à
--      transação, nunca sobrevive ao COMMIT/ROLLBACK — logo ANTES de tocar em qualquer linha, e nenhuma
--      outra função liga essa marca. Por que isso não abre brecha: (a) só DELETE é liberado, então não dá
--      para editar ou mascarar uma linha existente, só apagá-la; (b) a marca só existe dentro da mesma
--      transação da função SECURITY DEFINER já auditada e já sem EXECUTE para `plat_app` (009/
--      20260906T1601_funcoes_privilegiadas_isolamento.sql) — a aplicação não tem como ligá-la por conta
--      própria; (c) o único caminho que a liga apaga o inquilino inteiro (linha de `plat.tenant` incluída),
--      nunca apaga a auditoria de um inquilino que continua vivo.
--   3. O apagamento das linhas de `plat.auditoria` do inquilino deixa de vir do loop genérico dinâmico (que
--      ainda pegaria porque a tabela tem `tenant_id`) e vira um DELETE explícito, nomeado, na função —
--      excluído do loop para não depender de ordem/da lista de tabelas: apagar a trilha de auditoria de um
--      inquilino é ato deliberado, não efeito colateral de um loop genérico.
--
-- Teste de refutação: tests/api/test_auditoria_imutavel_apagar_inquilino.py.

CREATE OR REPLACE FUNCTION plat.tg_auditoria_imutavel() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE dono text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO dono FROM pg_class c WHERE c.oid = 'plat.auditoria'::regclass;
  IF coalesce(current_setting('plat.auditoria_expurgo', true), '') = '1' AND current_user = dono THEN
    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  -- apagamento do inquilino inteiro (plat.tenant_apagar_interno, ver comentário desta migração no topo do
  -- arquivo): só DELETE, com a marca local-à-transação ligada só por aquela função.
  IF TG_OP = 'DELETE' AND coalesce(current_setting('plat.apagando_inquilino', true), '') = '1' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'auditoria_imutavel'
    USING HINT = 'plat.auditoria é append-only: só plat.auditoria_expurgar() (como dono) ou apagar o '
      'inquilino inteiro (plat.tenant_apagar_interno) removem linha';
END $$;

CREATE OR REPLACE FUNCTION plat.tenant_apagar_interno(p_id int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text; r record; passo int; restantes int; apagadas int := 0;
BEGIN
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' THEN RAISE EXCEPTION 'plataforma_nao_apaga'; END IF;
  -- trinco por slug (hash do texto plat.camada_schema_prefixo()||slug): serializa contra qualquer criação/uso concorrente do
  -- schema de dado do mesmo inquilino nesta transação; liberado sozinho no COMMIT/ROLLBACK.
  PERFORM pg_advisory_xact_lock(hashtext(plat.camada_schema_prefixo() || s));
  -- o gatilho do último admin recusaria apagar o admin do inquilino que está sendo apagado: desligado só aqui, na
  -- mesma transação (DDL transacional: volta sozinho se algo falhar). Nunca por GUC, que plat_app poderia forjar.
  ALTER TABLE plat.usuario DISABLE TRIGGER usuario_ultimo_admin;
  -- marca local à transação (nunca sobrevive ao fim dela) que libera SÓ o DELETE em plat.auditoria feito
  -- por este apagamento — ver plat.tg_auditoria_imutavel() e o comentário do topo desta migração.
  PERFORM set_config('plat.apagando_inquilino', '1', true);
  -- linhas de auditoria do inquilino: apagadas aqui de forma explícita e nomeada, não deixadas para o loop
  -- genérico abaixo (que também as pegaria, por tenant_id, mas de forma dinâmica/implícita).
  DELETE FROM plat.auditoria WHERE tenant_id = p_id;
  -- referências que apontam para usuários do inquilino a partir de colunas sem cascata
  UPDATE plat.usuario SET papel_id = NULL WHERE tenant_id = p_id;
  UPDATE plat.token_servico SET renovado_por = NULL WHERE tenant_id = p_id;
  -- toda tabela do schema com tenant_id (inclusive as de outras linhas, como job/agenda), em passes até a ordem de
  -- FK fechar; partições ficam de fora (o pai apaga). auditoria sai da lista: já apagada explicitamente acima.
  FOR passo IN 1..6 LOOP
    restantes := 0;
    FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
             WHERE n.nspname = 'plat' AND c.relkind IN ('r', 'p') AND c.relname NOT IN ('tenant', 'auditoria')
               AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)
             ORDER BY c.relname LOOP
      BEGIN
        EXECUTE format('DELETE FROM plat.%I WHERE tenant_id = $1', r.relname) USING p_id;
        GET DIAGNOSTICS apagadas = ROW_COUNT;
      EXCEPTION WHEN foreign_key_violation THEN
        restantes := restantes + 1;
      END;
    END LOOP;
    EXIT WHEN restantes = 0;
  END LOOP;
  IF restantes > 0 THEN RAISE EXCEPTION 'inquilino_com_dependencias'; END IF;
  -- schema de dado do inquilino (camadas/tabelas próprias, L0-02-z): apagado por último, na mesma
  -- transação; CASCADE porque tudo lá dentro pertence só a este inquilino.
  EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', plat.camada_schema_prefixo() || s);
  DELETE FROM plat.tenant WHERE id = p_id;
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN p_id;
END $$;

REVOKE EXECUTE ON FUNCTION plat.tenant_apagar_interno(int) FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.tg_auditoria_imutavel() FROM PUBLIC, plat_app;
