-- 20260906T2110_jobs_justica_inquilino (item L0-05-e-justica-entre-inquilinos): escalonamento justo por inquilino
-- em plat.job_pegar. Antes a ordem era global (prioridade, agendado_para, criado_em): com 1 worker e dois jobs de
-- 300 s do inquilino B na frente, um job de 0 s do inquilino A esperava os 600 s inteiros (medido no T2).
-- Agora a primeira chave de ordenação é o TURNO do inquilino: max(iniciado_em) dos jobs daquele inquilino
-- (rodando ou já terminados), NULLS FIRST (inquilino nunca atendido é o mais atrasado no rodízio). Só depois
-- valem prioridade/agendado_para/criado_em — ou seja, a prioridade ordena a fila DENTRO do inquilino e o rodízio
-- alterna os inquilinos. Consequência medida: com 2 inquilinos e 1 worker, um job de A espera no máximo o job
-- de B que já está rodando (1 job de B), mesmo com 50 jobs longos de B enfileirados (teste do adversário em
-- tests/api/jobs/test_jobs_justica.py). Os filtros não mudam: chave em série, cota de simultâneos por inquilino
-- (plat.cota_jobs_simultaneos) e pesado continuam valendo. Sob concorrência de workers a escolha é por foto do
-- instante do SELECT (SKIP LOCKED destrava a corrida de pegar o MESMO job; dois workers podem, no limite, atender
-- o mesmo inquilino duas vezes seguidas — justiça é estatística sob concorrência, exata com 1 worker).
-- Índice parcial de apoio ao cálculo do turno (max(iniciado_em) por inquilino).
-- Idempotente (CREATE OR REPLACE + IF NOT EXISTS); assinatura e EXECUTEs da 006 não mudam.

CREATE INDEX IF NOT EXISTS ix_job_inquilino_turno ON plat.job (tenant_id, iniciado_em)
  WHERE iniciado_em IS NOT NULL;

CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
  WITH aptos AS (                       -- inquilinos com job pronto a rodar (só destes o turno interessa)
    SELECT DISTINCT j.tenant_id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
  ),
  turno AS (                            -- última vez que cada inquilino apto foi atendido
    SELECT r.tenant_id, max(r.iniciado_em) AS ultimo_inicio
    FROM plat.job r JOIN aptos a ON a.tenant_id = r.tenant_id
    WHERE r.iniciado_em IS NOT NULL
    GROUP BY r.tenant_id
  ),
  c AS (
    SELECT j.id FROM plat.job j
    LEFT JOIN turno t ON t.tenant_id = j.tenant_id
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r WHERE r.chave = j.chave AND r.estado = 'rodando'))
      AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
          < plat.cota_jobs_simultaneos(j.tenant_id)
    ORDER BY t.ultimo_inicio ASC NULLS FIRST, j.prioridade, j.agendado_para, j.criado_em
    FOR UPDATE OF j SKIP LOCKED LIMIT 1)
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = tentativa + 1, progresso = 0, mensagem = NULL
  FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;
