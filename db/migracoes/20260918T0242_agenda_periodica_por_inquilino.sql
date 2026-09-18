-- Agenda periódica POR INQUILINO (item L0-06-backup-status).
--
-- Achado do adversário do T9, medido em plat.agenda: os dois periódicos do backup por inquilino
-- (`backup.executar`, `backup.ensaio_restauracao`) existiam SÓ no inquilino técnico `plataforma`, porque
-- `plat.agenda_periodica_sincronizar` faz o upsert sempre lá. Um inquilino de cliente comum tinha ZERO
-- linha desses tipos — não pausada: AUSENTE. Rodando do jeito que estava, o "backup diário por inquilino"
-- que a hipótese do item promete faria backup de um schema só (`d_plataforma`), e o dono, ao ligar a
-- agenda, continuaria sem backup de cliente nenhum, sem nenhum aviso.
--
-- Esta função é a irmã por inquilino daquela: um upsert por inquilino ATIVO, com o mesmo contrato
-- (`ON CONFLICT (tenant_id, nome)` atualiza tipo/parâmetros/cron/fuso e NÃO toca `ativa`), e devolve
-- quantas linhas tocou.
--
-- `ativa` na criação é parâmetro, e quem chama passa `false` para os dois do backup: a decisão de que
-- esses dois nascem pausados "para o dono decidir" é de outro item (migração 20260910T2210) e continua
-- valendo. O que muda aqui é que, quando o dono ligar, existe o que ligar em CADA inquilino.
CREATE OR REPLACE FUNCTION plat.agenda_periodica_por_inquilino_sincronizar(
  p_nome text, p_tipo text, p_parametros jsonb, p_cron text, p_fuso text,
  p_proxima_em timestamptz, p_ativa_na_criacao boolean DEFAULT false
) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'plat', 'public'
AS $$
DECLARE n int := 0;
BEGIN
  INSERT INTO plat.agenda (tenant_id, usuario_id, nome, tipo, parametros, cron, fuso, proxima_em, ativa)
  SELECT t.id, NULL, p_nome, p_tipo, p_parametros, p_cron, p_fuso, p_proxima_em, p_ativa_na_criacao
    FROM plat.tenant t
   WHERE t.ativo
  ON CONFLICT (tenant_id, nome) DO UPDATE
     SET tipo = EXCLUDED.tipo, parametros = EXCLUDED.parametros, cron = EXCLUDED.cron, fuso = EXCLUDED.fuso,
         proxima_em = CASE WHEN plat.agenda.cron <> EXCLUDED.cron
                             OR (plat.agenda.proxima_em IS NULL AND plat.agenda.ativa)
                           THEN EXCLUDED.proxima_em ELSE plat.agenda.proxima_em END;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

REVOKE ALL ON FUNCTION plat.agenda_periodica_por_inquilino_sincronizar(text, text, jsonb, text, text, timestamptz, boolean) FROM PUBLIC;
-- quem chama e o WORKER, na partida (app/jobs/agenda.py::sincronizar_periodicos): mesmo GRANT da funcao irma.
GRANT EXECUTE ON FUNCTION plat.agenda_periodica_por_inquilino_sincronizar(text, text, jsonb, text, text, timestamptz, boolean) TO plat_worker;
