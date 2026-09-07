-- 20260907T1720_log_acesso_req_id: item L7-06-c-logs-consulta-req-id. Acrescenta `req_id` a
-- `plat.log_acesso` (correlação com a linha JSON do journal e, via application_name, com o Postgres —
-- ver app/log.py e app/db.py) e ao filtro de `plat.log_registrar`. Idempotente; ALTER TABLE ADD COLUMN
-- e CREATE INDEX num pai particionado cascateiam para as partições existentes (Postgres >= 11).

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('log/nivel_definir', 'nível de log em tempo de execução definido/alterado (superadmin; componente, nível, prazo)'),
  ('log/nivel_remover', 'override de nível de log removido antes do prazo (superadmin)')
ON CONFLICT (nome) DO NOTHING;

ALTER TABLE plat.log_acesso ADD COLUMN IF NOT EXISTS req_id text;
CREATE INDEX IF NOT EXISTS ix_log_acesso_tenant_req ON plat.log_acesso (tenant_id, req_id)
  WHERE req_id IS NOT NULL;

-- A versão de 11 argumentos (migração 003) FICA: `tests/api/test_rls.py` e `test_funcoes_seguras.py` a chamam
-- e a aridade diferente não gera ambiguidade. A nova é uma sobrecarga, não uma substituição.
CREATE OR REPLACE FUNCTION plat.log_registrar(p_tenant int, p_usuario int, p_token int, p_ip text, p_metodo text,
  p_rota text, p_status int, p_bytes bigint, p_tempo_ms int, p_agente text, p_resultado text, p_req_id text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF p_tenant IS NOT NULL AND plat.tenant_atual() IS NOT NULL AND p_tenant <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'contexto_de_outro_inquilino';
  END IF;
  BEGIN
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente,
                                 resultado, req_id)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado, left(p_req_id, 40));
  EXCEPTION WHEN check_violation THEN
    PERFORM plat.log_particao_garantir(now()::date);
    INSERT INTO plat.log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes, tempo_ms, agente,
                                 resultado, req_id)
    VALUES (p_tenant, p_usuario, p_token, p_ip, p_metodo, left(p_rota, 500), p_status, coalesce(p_bytes, 0),
            p_tempo_ms, left(p_agente, 200), p_resultado, left(p_req_id, 40));
  END;
END $$;
REVOKE ALL ON FUNCTION plat.log_registrar(int, int, int, text, text, text, int, bigint, int, text, text, text)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.log_registrar(int, int, int, text, text, text, int, bigint, int, text, text, text)
  TO plat_app;

-- A sobrecarga de 11 argumentos continua existindo para quem ainda a chama (tests/api/test_rls.py,
-- tests/api/test_funcoes_seguras.py e qualquer base já migrada): passa a delegar na de 12 com req_id nulo,
-- para haver UM só caminho de INSERT em plat.log_acesso.
CREATE OR REPLACE FUNCTION plat.log_registrar(p_tenant int, p_usuario int, p_token int, p_ip text, p_metodo text,
  p_rota text, p_status int, p_bytes bigint, p_tempo_ms int, p_agente text, p_resultado text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  PERFORM plat.log_registrar(p_tenant, p_usuario, p_token, p_ip, p_metodo, p_rota, p_status, p_bytes, p_tempo_ms,
                             p_agente, p_resultado, NULL);
END $$;
REVOKE ALL ON FUNCTION plat.log_registrar(int, int, int, text, text, text, int, bigint, int, text, text)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.log_registrar(int, int, int, text, text, text, int, bigint, int, text, text)
  TO plat_app;
