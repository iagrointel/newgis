-- Conserto do grupo G4 (laudo laco/handoffs/T3/ataque-g4-ADVERSARIO.md, achados G4-04/05, G4-06/07/08/09, G4-10).
-- Cinco mudanças, todas idempotentes:
--   1. teto de cota por inquilino em plat.tenant (colunas + gatilho): o inquilino escolhe abaixo do teto, a
--      plataforma escolhe o teto (plat.tenant_cotas_teto_definir, que exige sessão de superadmin);
--   2. plat.cota_usuarios passa a devolver o MENOR entre o que o inquilino pediu e o teto;
--   3. plat.arquivo_apagado_marcar: marca a linha de plat.arquivo como apagada com o inquilino EXPLÍCITO, para
--      que app/objetos.py::apagar deixe de depender de um contexto de sessão que ele não tem;
--   4. plat.evento_expurgar / plat.log_expurgar validam o argumento e deixam de ser executáveis por plat_app;
--      quem precisa expurgar o rastro de UM inquilino usa as funções _inquilino, que filtram por tenant_id;
--   5. tipos de evento novos (arquivos/*, importacoes/apagar, inquilinos/cotas_teto, usuarios/*).

-- ---------------------------------------------------------------- 1. teto de cota (G4-04, G4-05)
ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS cota_bytes_teto bigint NOT NULL DEFAULT 21474836480;
ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS cota_usuarios_teto int NOT NULL DEFAULT 2000;
-- inquilino que já estava acima do teto padrão (base antiga) sobe o teto até o que ele já usava, nunca desce a
-- cota por baixo do pé de quem já gravou: o teto nasce >= cota vigente.
UPDATE plat.tenant SET cota_bytes_teto = cota_bytes WHERE cota_bytes > cota_bytes_teto;
UPDATE plat.tenant SET cota_usuarios_teto = (config->>'cota_usuarios')::int
 WHERE (config->>'cota_usuarios') ~ '^[0-9]+$' AND (config->>'cota_usuarios')::int > cota_usuarios_teto;

CREATE OR REPLACE FUNCTION plat.tenant_cota_guarda() RETURNS trigger
LANGUAGE plpgsql SET search_path = plat, public AS $$
DECLARE pedido_usuarios int;
BEGIN
  IF (NEW.cota_bytes_teto IS DISTINCT FROM OLD.cota_bytes_teto
      OR NEW.cota_usuarios_teto IS DISTINCT FROM OLD.cota_usuarios_teto)
     AND coalesce(current_setting('plat.teto_definir', true), '') <> 'on' THEN
    RAISE EXCEPTION 'teto_e_da_plataforma'
      USING HINT = 'cota_bytes_teto/cota_usuarios_teto só mudam por plat.tenant_cotas_teto_definir';
  END IF;
  IF NEW.cota_bytes > NEW.cota_bytes_teto THEN
    RAISE EXCEPTION 'cota_acima_do_teto'
      USING HINT = format('cota_bytes %s acima do teto %s', NEW.cota_bytes, NEW.cota_bytes_teto);
  END IF;
  pedido_usuarios := CASE WHEN (NEW.config->>'cota_usuarios') ~ '^[0-9]+$'
                          THEN (NEW.config->>'cota_usuarios')::int ELSE NULL END;
  IF pedido_usuarios IS NOT NULL AND pedido_usuarios > NEW.cota_usuarios_teto THEN
    RAISE EXCEPTION 'cota_acima_do_teto'
      USING HINT = format('cota_usuarios %s acima do teto %s', pedido_usuarios, NEW.cota_usuarios_teto);
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_tenant_cota_guarda ON plat.tenant;
CREATE TRIGGER tg_tenant_cota_guarda BEFORE UPDATE ON plat.tenant
  FOR EACH ROW EXECUTE FUNCTION plat.tenant_cota_guarda();

-- Teto absoluto da instalação: nem a plataforma escreve um teto arbitrário (o 9e18 do ataque não passa nem aqui).
CREATE OR REPLACE FUNCTION plat.tenant_cotas_teto_definir(
  p_sessao_hash text, p_id int, p_cota_bytes_teto bigint, p_cota_usuarios_teto int) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE bytes_abs bigint := 1099511627776;  -- 1 TiB
        usuarios_abs int := 100000;
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  IF p_cota_bytes_teto IS NULL OR p_cota_bytes_teto < 104857600 OR p_cota_bytes_teto > bytes_abs THEN
    RAISE EXCEPTION 'teto_fora_do_intervalo' USING HINT = format('cota_bytes_teto entre 104857600 e %s', bytes_abs);
  END IF;
  IF p_cota_usuarios_teto IS NULL OR p_cota_usuarios_teto < 1 OR p_cota_usuarios_teto > usuarios_abs THEN
    RAISE EXCEPTION 'teto_fora_do_intervalo' USING HINT = format('cota_usuarios_teto entre 1 e %s', usuarios_abs);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  PERFORM set_config('plat.teto_definir', 'on', true);
  UPDATE plat.tenant SET cota_bytes_teto = p_cota_bytes_teto, cota_usuarios_teto = p_cota_usuarios_teto,
         cota_bytes = least(cota_bytes, p_cota_bytes_teto),
         config = CASE WHEN (config->>'cota_usuarios') ~ '^[0-9]+$'
                            AND (config->>'cota_usuarios')::int > p_cota_usuarios_teto
                       THEN config || jsonb_build_object('cota_usuarios', p_cota_usuarios_teto)
                       ELSE config END
   WHERE id = p_id;
  PERFORM set_config('plat.teto_definir', 'off', true);
END $$;
CREATE OR REPLACE FUNCTION plat.tenant_cotas(p_sessao_hash text, p_id int)
RETURNS TABLE(id int, slug text, cota_bytes bigint, cota_bytes_teto bigint, cota_usuarios int,
              cota_usuarios_teto int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.plataforma_operador(p_sessao_hash);
  RETURN QUERY
    SELECT t.id, t.slug, t.cota_bytes, t.cota_bytes_teto,
           least(coalesce((t.config->>'cota_usuarios')::int, 2000), t.cota_usuarios_teto), t.cota_usuarios_teto
      FROM plat.tenant t WHERE t.id = p_id;
END $$;
REVOKE EXECUTE ON FUNCTION plat.tenant_cotas(text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_cotas(text, int) TO plat_app;

REVOKE EXECUTE ON FUNCTION plat.tenant_cotas_teto_definir(text, int, bigint, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_cotas_teto_definir(text, int, bigint, int) TO plat_app;

-- ---------------------------------------------------------------- 2. cota efetiva de usuários (G4-05)
CREATE OR REPLACE FUNCTION plat.cota_usuarios(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT least(coalesce((config->>'cota_usuarios')::int, 2000), cota_usuarios_teto)
    FROM plat.tenant WHERE id = p_tenant
$$;
REVOKE EXECUTE ON FUNCTION plat.cota_usuarios(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.cota_usuarios(int) TO plat_app;

-- ---------------------------------------------------------------- 3. marcar arquivo apagado (G4-09)
-- app/objetos.py::apagar() resolve o bucket pelo SLUG da chave, fora de qualquer sessão; a política RLS
-- p_arquivo (tenant_id = plat.tenant_atual()) casava com zero linhas e o UPDATE sumia em silêncio. Aqui o
-- inquilino é ARGUMENTO, não GUC, e a função é do definidor — mesmo padrão de plat.arquivo_bucket_resolver.
CREATE OR REPLACE FUNCTION plat.arquivo_apagado_marcar(p_tenant_id int, p_chave text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  UPDATE plat.arquivo SET apagado_em = now()
   WHERE tenant_id = p_tenant_id AND chave = p_chave AND apagado_em IS NULL;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.arquivo_apagado_marcar(int, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.arquivo_apagado_marcar(int, text) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.arquivo_apagado_marcar(int, text) TO plat_worker;

-- ---------------------------------------------------------------- 4. expurgo de rastro (G4-10)
-- Antes: SECURITY DEFINER, sem validar o argumento (meses negativo levava o limite para o FUTURO e derrubava a
-- partição do mês corrente), sem filtro de inquilino, e com EXECUTE para plat_app pelo GRANT em bloco da 001.
CREATE OR REPLACE FUNCTION plat.evento_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  IF limite >= date_trunc('month', now())::date THEN
    RAISE EXCEPTION 'limite_no_presente' USING HINT = 'o expurgo nunca alcança a partição do mês corrente';
  END IF;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.evento'::regclass LOOP
    IF to_date(substring(r.relname FROM 'y(\d{4})m(\d{2})$'), 'YYYY') IS NOT NULL
       AND (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.log_expurgar(p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r record; n int := 0; limite date;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  limite := (date_trunc('month', now()) - make_interval(months => p_meses))::date;
  IF limite >= date_trunc('month', now())::date THEN
    RAISE EXCEPTION 'limite_no_presente' USING HINT = 'o expurgo nunca alcança a partição do mês corrente';
  END IF;
  FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
           WHERE i.inhparent = 'plat.log_acesso'::regclass LOOP
    IF (to_date(regexp_replace(r.relname, '^.*y(\d{4})m(\d{2})$', '\1\2'), 'YYYYMM') + interval '1 month')::date <= limite THEN
      EXECUTE format('DROP TABLE plat.%I', r.relname);
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;

-- Expurgo COM filtro de inquilino: apaga linha, nunca partição, e nunca alcança o rastro de outro inquilino.
CREATE OR REPLACE FUNCTION plat.evento_expurgar_inquilino(p_tenant_id int, p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; limite timestamptz;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  IF p_tenant_id IS NULL OR NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  limite := date_trunc('month', now()) - make_interval(months => p_meses);
  DELETE FROM plat.evento WHERE tenant_id = p_tenant_id AND em < limite;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

CREATE OR REPLACE FUNCTION plat.log_expurgar_inquilino(p_tenant_id int, p_meses int DEFAULT 12) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; limite timestamptz;
BEGIN
  IF p_meses IS NULL OR p_meses < 1 OR p_meses > 1200 THEN
    RAISE EXCEPTION 'meses_invalido' USING HINT = 'retenção em meses inteiros entre 1 e 1200';
  END IF;
  IF p_tenant_id IS NULL OR NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant_id) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  limite := date_trunc('month', now()) - make_interval(months => p_meses);
  DELETE FROM plat.log_acesso WHERE tenant_id = p_tenant_id AND em < limite;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Quem não precisa, não executa. O papel da aplicação (plat_app) NUNCA expurga rastro; o periódico de retenção
-- é do worker, e mesmo ele só alcança o expurgo por inquilino. O expurgo global fica com o dono do banco.
REVOKE EXECUTE ON FUNCTION plat.evento_expurgar(int) FROM PUBLIC, plat_app, plat_worker;
REVOKE EXECUTE ON FUNCTION plat.log_expurgar(int) FROM PUBLIC, plat_app, plat_worker;
REVOKE EXECUTE ON FUNCTION plat.evento_expurgar_inquilino(int, int) FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.log_expurgar_inquilino(int, int) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.evento_expurgar_inquilino(int, int) TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.log_expurgar_inquilino(int, int) TO plat_worker;

-- ---------------------------------------------------------------- 5. vocabulário de evento novo
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('arquivos/enviar', 'objeto genérico gravado no armazenamento do inquilino'),
  ('arquivos/apagar', 'objeto genérico apagado do armazenamento do inquilino'),
  ('importacoes/apagar', 'importação descartada antes da confirmação'),
  ('inquilinos/cotas_teto', 'a plataforma alterou o teto de cota de um inquilino'),
  ('usuarios/redefinir_senha_pedido', 'pedido de redefinição de senha por e-mail'),
  ('usuarios/2fa_iniciar', 'segredo TOTP novo gerado para a conta (antes da confirmação)')
ON CONFLICT (nome) DO NOTHING;
