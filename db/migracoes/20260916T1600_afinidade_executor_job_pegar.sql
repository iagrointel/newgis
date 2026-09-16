-- depende: 20260916T1100_recurso_partilhado_por_inquilino_regressao.sql
--
-- Decisão G7 do gerente: afinidade de executor em plat.job_pegar (achado
-- tests/api/conexao/test_google_sheets.py + test_wfs_ogcapi.py, 16/09/2026).
--
-- SINTOMA: os dois arquivos sobem um worker PRIVADO em subprocesso (com a CA de teste e a válvula de
-- alvo liberado, PLAT_TESTE_CONEXAO_ALVOS) para provar `conexoes.arquivo_sincronizar` ponta a ponta.
-- O worker do systemd da trilha (mesma fila `plat.job`) corre pelo MESMO job de sincronização e às
-- vezes vence a corrida — ele não tem a CA de teste nem a válvula, e falha com
-- `erro_de_conexao:ConnectError`. É corrida por desenho da fila (qualquer worker pega qualquer job),
-- não bug do conector.
--
-- CONSERTO: a coluna `plat.job.executor` (texto livre até aqui, só metadado do TIPO de job) vira
-- AFINIDADE de worker. Um job "genérico" (executor local/gpu — todo o tráfego de produção de hoje)
-- continua podendo ir para QUALQUER worker: isso não pode regredir. Um job "teste:<pid>" (marcado
-- assim pela válvula test-only `PLAT_TESTE_JOB_EXECUTOR` em app/jobs/sistema.py::enfileirar) só pode
-- ir para o worker que anuncia EXATAMENTE esse mesmo "teste:<pid>" como o novo 3º argumento de
-- `job_pegar` (`p_executor`, default 'padrao' — o que qualquer worker não atualizado, inclusive o do
-- systemd já rodando, continua anunciando implicitamente).
--
-- Por que DROP antes de CREATE (e não só acrescentar o parâmetro): Postgres não troca a assinatura de
-- uma função por `CREATE OR REPLACE` quando a LISTA de tipos de parâmetro muda (2 params -> 3 params,
-- mesmo o 3º tendo DEFAULT) — ele cria uma SEGUNDA função (sobrecarga), e a partir daí uma chamada com
-- 2 argumentos fica AMBÍGUA ("is not unique"), não cai na antiga nem na nova. Medido ao vivo nesta
-- trilha antes de escrever esta migração (pg_temp, duas funções de teste). Por isso a função de 2
-- argumentos é DERRUBADA primeiro: sobra UMA função (3 parâmetros, o 3º com default), e só assim toda
-- chamada de 2 argumentos que já existe na árvore (worker do systemd ainda não atualizado incluso,
-- tests/api/adversario_g3, test_alertas_metricas.py, test_sync_esri.py, test_jobs_transicoes.py,
-- test_eventos_e_seguranca.py) continua funcionando sem alteração, agora recebendo p_executor='padrao'
-- pelo default. O worker do systemd `plat-uniao-worker` nunca precisa ser parado nem reiniciado para
-- este conserto valer: ele passa a anunciar 'padrao' pelo simples fato de não passar o 3º argumento, o
-- que já basta para nunca disputar um job 'teste:%'.
--
-- A cláusula de afinidade entra nos DOIS CTEs que filtram job pendente (`aptos`, que decide o turno
-- por inquilino, e `c`, que escolhe o job final) — só em um dos dois o cálculo de turno ficaria errado
-- quando o único job pendente de um inquilino é um job de teste que este worker não pode pegar.

DROP FUNCTION IF EXISTS plat.job_pegar(text, boolean);

CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean, p_executor text DEFAULT 'padrao') RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
  WITH aptos AS (                       -- inquilinos com job pronto a rodar (só destes o turno interessa)
    SELECT DISTINCT j.tenant_id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.somente_leitura OR NOT plat.modo_bloqueia(j.tenant_id))
      -- afinidade de executor (G7): job "teste:%" só é apto para o turno do worker que anuncia o
      -- mesmo p_executor; job genérico (local/gpu) segue apto para qualquer worker (não regride)
      AND (j.executor NOT LIKE 'teste:%' OR j.executor = p_executor)
  ),
  turno AS (                            -- última vez que cada inquilino apto foi atendido
    SELECT j.tenant_id, max(j.iniciado_em) AS ultimo_inicio
    FROM plat.job j JOIN aptos a ON a.tenant_id = j.tenant_id
    WHERE j.iniciado_em IS NOT NULL
    GROUP BY j.tenant_id
  ),
  c AS (
    SELECT j.id FROM plat.job j
    LEFT JOIN turno t ON j.tenant_id = t.tenant_id
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.somente_leitura OR NOT plat.modo_bloqueia(j.tenant_id))
      -- mesma afinidade de executor, agora na escolha final (achado: sem repetir aqui, um worker sem
      -- afinidade podia pegar um job 'teste:%' que só passou no CTE aptos por causa de OUTRO job do
      -- mesmo inquilino)
      AND (j.executor NOT LIKE 'teste:%' OR j.executor = p_executor)
      -- o trinco é do INQUILINO: mesma chave em inquilinos diferentes não se estorva (achado g3)
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r
             WHERE r.chave = j.chave AND r.tenant_id = j.tenant_id AND r.estado = 'rodando'))
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

-- mesmo contrato de privilégio da 013_jobs_execute_reafirma.sql: só plat_worker muda estado de job. O
-- DROP acima apagou a ACL da função antiga (dropar função apaga ACL junto); sem isto, o CREATE novo
-- nasceria só com o privilégio padrão de plat_app (ALTER DEFAULT PRIVILEGES da 001_fundacao.sql).
REVOKE EXECUTE ON FUNCTION plat.job_pegar(text, boolean, text) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.job_pegar(text, boolean, text) TO plat_worker;

-- a coluna já existe (`plat.job.executor text NOT NULL DEFAULT 'local'`, 004_jobs.sql); alargar só a
-- lista fechada do CHECK para caber a identidade que o worker de teste anuncia. 'padrao' (identidade
-- que o worker COMUM anuncia como 3º argumento de job_pegar) nunca é gravado em `executor` de job de
-- verdade — só 'local'/'gpu' (registro do tipo) ou 'teste:<pid>' (enfileiramento de teste) entram aqui.
ALTER TABLE plat.job DROP CONSTRAINT IF EXISTS job_executor_check;
ALTER TABLE plat.job ADD CONSTRAINT job_executor_check
  CHECK (executor = ANY (ARRAY['local', 'gpu']) OR executor ~ '^teste:[0-9]+$');
