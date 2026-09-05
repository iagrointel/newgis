-- 009_inquilino_apagar: apagar inquilino (achado do testador do T2: 7 inquilinos zt-inq-* sem rota de apagar).
-- plat.tenant_apagar_interno(p_id): apaga TUDO do inquilino em ordem de dependência (só postgres executa; o
-- install.sh a usa para limpar resíduos zt-* em dev). plat.tenant_apagar(p_sessao_hash, p_id): a mesma coisa para o
-- superadmin resolvido pela sessão (ADR 0002 seção 10), recusando `plataforma`. Idempotente. Sem BEGIN/COMMIT.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES ('inquilinos/apagar', 'inquilino apagado pelo superadmin')
ON CONFLICT (nome) DO NOTHING;

CREATE OR REPLACE FUNCTION plat.tenant_apagar_interno(p_id int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE s text; r record; passo int; restantes int; apagadas int := 0;
BEGIN
  SELECT slug INTO s FROM plat.tenant WHERE id = p_id;
  IF s IS NULL THEN RAISE EXCEPTION 'inquilino_inexistente'; END IF;
  IF s = 'plataforma' THEN RAISE EXCEPTION 'plataforma_nao_apaga'; END IF;
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
  DELETE FROM plat.tenant WHERE id = p_id;
  ALTER TABLE plat.usuario ENABLE TRIGGER usuario_ultimo_admin;
  RETURN p_id;
END $$;

CREATE OR REPLACE FUNCTION plat.tenant_apagar(p_sessao_hash text, p_id int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN plat.tenant_apagar_interno(p_id);
END $$;

REVOKE EXECUTE ON FUNCTION plat.tenant_apagar_interno(int) FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.tenant_apagar(text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_apagar(text, int) TO plat_app;
