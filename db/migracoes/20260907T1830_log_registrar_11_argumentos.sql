-- depende: 20260907T1720_log_acesso_req_id.sql
-- Item L7-06-c. A migração anterior acrescentou plat.log_registrar com 12 argumentos (o req_id). Em base
-- onde a versão de 11 argumentos tinha sido apagada por uma execução anterior desta linha de trabalho, a
-- chamada de 11 argumentos deixou de resolver ("function ... does not exist"), e dois testes que a usam
-- (tests/api/test_rls.py e tests/api/test_funcoes_seguras.py) reprovaram. Esta migração recria a
-- sobrecarga de 11 argumentos como uma casca fina sobre a de 12, para haver UM só caminho de INSERT em
-- plat.log_acesso. Idempotente e sem DROP: aridade diferente não gera ambiguidade.
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
