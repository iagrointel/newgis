-- 20260907T1320_fila_job_mais_antigo: item L7-34-saude-profunda. A sonda de fila do /saude/profunda precisa da
-- idade do job pendente mais antigo (não só a contagem que plat.fila_estado() já dá). Mesma justificativa de
-- plat.fila_estado(): SECURITY DEFINER porque a sonda de saúde não tem tenant — ela pergunta pela fila inteira.
CREATE OR REPLACE FUNCTION plat.fila_job_mais_antigo_pendente_s()
RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT EXTRACT(EPOCH FROM (now() - min(criado_em))) FROM plat.job WHERE estado = 'pendente'
$$;

GRANT EXECUTE ON FUNCTION plat.fila_job_mais_antigo_pendente_s() TO plat_app;
