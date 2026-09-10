-- 20260910T2307_inquilino_apagar_schema: L0-02-z-apagar-inquilino-apaga-schema.
-- plat.tenant_apagar_interno apagava só as linhas plat.* com tenant_id; o schema de dado do inquilino
-- (d_<slug>, criado por app/plataforma na hora de provisionar camadas/tabelas próprias) nunca era
-- removido — medido ao vivo em 10/09: DELETE /api/plataforma/inquilinos/{id} devolvia 204 e o schema
-- d_<slug> continuava em pg_namespace, com a tabela do inquilino dentro. Corrige na MESMA transação
-- (CREATE OR REPLACE mantém SECURITY DEFINER como postgres, dono de todo schema d_*; trinco por slug
-- via advisory lock evita corrida com uma criação de schema em andamento para o mesmo slug).

CREATE OR REPLACE FUNCTION plat.tenant_apagar_interno(p_id int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text; r record; passo int; restantes int; apagadas int := 0;
BEGIN
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' THEN RAISE EXCEPTION 'plataforma_nao_apaga'; END IF;
  -- trinco por slug (hash do texto 'd_'||slug): serializa contra qualquer criação/uso concorrente do
  -- schema de dado do mesmo inquilino nesta transação; liberado sozinho no COMMIT/ROLLBACK.
  PERFORM pg_advisory_xact_lock(hashtext('d_' || s));
  -- o gatilho do último admin recusaria apagar o admin do inquilino que está sendo apagado: desligado só aqui, na
  -- mesma transação (DDL transacional: volta sozinho se algo falhar). Nunca por GUC, que plat_app poderia forjar.
  ALTER TABLE plat.usuario DISABLE TRIGGER usuario_ultimo_admin;
  -- referências que apontam para usuários do inquilino a partir de colunas sem cascata
  UPDATE plat.usuario SET papel_id = NULL WHERE tenant_id = p_id;
  UPDATE plat.token_servico SET renovado_por = NULL WHERE tenant_id = p_id;
  -- toda tabela do schema com tenant_id (inclusive as de outras linhas, como job/agenda), em passes até a ordem de
  -- FK fechar; partições ficam de fora (o pai apaga)
  FOR passo IN 1..6 LOOP
    restantes := 0;
    FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
             WHERE n.nspname = 'plat' AND c.relkind IN ('r', 'p') AND c.relname <> 'tenant'
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
  EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', 'd_' || s);
  DELETE FROM plat.tenant WHERE id = p_id;
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN p_id;
END $$;

REVOKE EXECUTE ON FUNCTION plat.tenant_apagar_interno(int) FROM PUBLIC, plat_app;
