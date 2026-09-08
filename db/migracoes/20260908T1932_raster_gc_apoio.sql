-- Item L1-01-i (coleta de lixo das imagens): apoio de banco para o CLI `plat raster gc`.
--
-- 1) `tenants_para_manutencao()`: o CLI percorre cada inquilino, mas `plat.tenant` tem RLS
--    `id = tenant_atual()` — o papel do aplicativo, sem sessão de inquilino, não vê linha nenhuma.
--    Esta leitura SECURITY DEFINER devolve só `id` e `slug` (nunca cota, config ou segredo) para
--    ENUMERAR os inquilinos na manutenção; todo o trabalho de coleta continua sob o contexto de
--    cada inquilino, com a RLS dele.
--
-- 2) `job_registrar_concluido()`: o gatilho `plat.job_transicao` não aceita job nascendo 'concluido'
--    nem transição fora do GUC `plat.via_worker` — e `via_worker_ligar` só é executável pela role
--    plat_worker. Quando a PRÓPRIA CLI executou o trabalho (a coleta) e quer o relatório visível em
--    Tarefas, o caminho honesto pela máquina de estados é: nasce pendente (`jobs.sistema.enfileirar`,
--    com a mesma cota diária), depois ESTA função o põe 'rodando' e conclui por `plat.job_terminar`
--    (que reusa os mesmos disparos de notificação do worker). Só aceita job PENDENTE recém-criado —
--    um job em execução por um worker de verdade não é tocado.
CREATE OR REPLACE FUNCTION plat.tenants_para_manutencao()
RETURNS TABLE (id integer, slug text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = plat, pg_temp
AS $fn$
  SELECT t.id, t.slug FROM plat.tenant t ORDER BY t.id
$fn$;

CREATE OR REPLACE FUNCTION plat.job_registrar_concluido(p_id uuid, p_worker text, p_resultado jsonb, p_proveniencia jsonb)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = plat, pg_temp
AS $fn$
DECLARE n int;
BEGIN
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = 1
  WHERE id = p_id AND estado = 'pendente';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n = 0 THEN
    PERFORM plat.via_worker_desligar();
    RETURN false;  -- o job já não é mais nosso (tomado por um worker de verdade): nada a concluir
  END IF;
  RETURN plat.job_terminar(p_id, p_worker, 'concluido', p_resultado, NULL, p_proveniencia);
END $fn$;

REVOKE ALL ON FUNCTION plat.tenants_para_manutencao() FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.job_registrar_concluido(uuid, text, jsonb, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenants_para_manutencao() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.tenants_para_manutencao() TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.job_registrar_concluido(uuid, text, jsonb, jsonb) TO plat_app;
