-- 014_jobs_semear_demo (T2, correção 3 do L0-05, achado do testador): o e2e dos 1.000 jobs semeava por SQL direto
-- (INSERT já 'concluido' como plat_app) e a migração 006 passou a barrar isso, corretamente. Em vez de afrouxar a
-- 006 entra uma função de DEMONSTRAÇÃO de nome explícito, plat.jobs_semear_demo, com quatro guardas independentes:
--   1. INTERRUPTOR de configuração, desligado por padrão: plat.ambiente.semear_demo, escrito só pelo install.sh
--      (true quando PLAT_AMBIENTE=dev ou PLAT_SEMENTE_DEMO=sim no .env). plat_app tem SELECT e nada mais nessa
--      tabela, logo não consegue ligar o interruptor; numa instalação de cliente a chave não existe e fica false.
--   2. INQUILINO de demonstração: só 'demo', 'demo2' e os 'zt-%' da suíte; inquilino de cliente nunca é semeado,
--      mesmo com o interruptor ligado.
--   3. ESTADO TERMINAL: só cria job em 'concluido'/'falhou'/'cancelado' — nunca 'pendente' visível ao worker nem
--      'rodando'. A fila real não é alimentada por esta função e nenhum resultado de execução é forjado.
--   4. TETO e MARCA: no máximo 5.000 por chamada, sempre no inquilino do contexto, sempre com
--      parametros->>'semente_demo' = 'true' (é por essa marca que o teste apaga o que semeou).
-- A 006 NÃO é afrouxada: o gatilho plat.job_transicao continua com o texto da 006 e nenhum privilégio de plat_app
-- muda. A função insere o job 'pendente' e limpo (o que o gatilho de INSERT já permite a qualquer chamador) e só
-- então faz a transição para o estado final pelo MESMO caminho do worker (plat.via_worker_ligar dentro de
-- SECURITY DEFINER, cujo EXECUTE plat_app não tem e não passa a ter).
-- Idempotente; sem BEGIN/COMMIT.

-- ---------------------------------------------------------------- 1. o banco sabe em que ambiente está
CREATE TABLE IF NOT EXISTS plat.ambiente (
  unico       boolean PRIMARY KEY DEFAULT true CHECK (unico),
  nome        text NOT NULL CHECK (nome IN ('dev', 'producao')),   -- mesmos valores de AMBIENTES em app/settings.py
  semear_demo boolean NOT NULL DEFAULT false,                      -- interruptor da função de demonstração abaixo
  definido_em timestamptz NOT NULL DEFAULT now()
);
-- padrão fecha: sem install.sh o banco se declara 'producao' com a semeadura desligada
INSERT INTO plat.ambiente (unico, nome, semear_demo) VALUES (true, 'producao', false) ON CONFLICT (unico) DO NOTHING;
-- a 001 dá SELECT/INSERT/UPDATE/DELETE a plat_app em toda tabela nova do schema (ALTER DEFAULT PRIVILEGES):
-- aqui o REVOKE para plat_app tem de ser explícito, senão a API vira o próprio interruptor (MEDIDO: sem esta
-- linha, `UPDATE plat.ambiente SET semear_demo = true` como plat_app passava)
REVOKE ALL ON plat.ambiente FROM PUBLIC;
REVOKE ALL ON plat.ambiente FROM plat_app;
GRANT SELECT ON plat.ambiente TO plat_app;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_worker') THEN
    REVOKE ALL ON plat.ambiente FROM plat_worker;
    GRANT SELECT ON plat.ambiente TO plat_worker;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION plat.ambiente_atual() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT coalesce((SELECT nome FROM plat.ambiente WHERE unico), 'producao') $$;
CREATE OR REPLACE FUNCTION plat.semente_demo_habilitada() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce((SELECT semear_demo FROM plat.ambiente WHERE unico), false) $$;
REVOKE EXECUTE ON FUNCTION plat.ambiente_atual() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.semente_demo_habilitada() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.ambiente_atual() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.semente_demo_habilitada() TO plat_app;

-- ---------------------------------------------------------------- 2. semeadura de demonstração
DROP FUNCTION IF EXISTS plat.jobs_semear_demo(int, text, jsonb, text);
CREATE FUNCTION plat.jobs_semear_demo(p_quantos int, p_tipo text, p_parametros jsonb DEFAULT '{}'::jsonb,
                                      p_estado text DEFAULT 'concluido')
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t int := plat.tenant_atual(); u int := plat.usuario_atual(); slug text; n int; ids uuid[];
BEGIN
  IF NOT plat.semente_demo_habilitada() THEN
    RAISE EXCEPTION 'semeadura de demonstração desligada (plat.ambiente.semear_demo = false, ambiente %)',
      plat.ambiente_atual() USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF t IS NULL OR u IS NULL THEN
    RAISE EXCEPTION 'jobs_semear_demo exige contexto de inquilino e usuário' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT tn.slug INTO slug FROM plat.tenant tn WHERE tn.id = t;
  IF slug IS NULL OR NOT (slug IN ('demo', 'demo2') OR slug LIKE 'zt-%') THEN
    RAISE EXCEPTION 'jobs_semear_demo só semeia inquilino de demonstração (demo, demo2, zt-%%), não %', slug
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_estado NOT IN ('concluido', 'falhou', 'cancelado') THEN
    RAISE EXCEPTION 'jobs_semear_demo só cria job em estado final (concluido, falhou, cancelado), não %', p_estado
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF p_quantos IS NULL OR p_quantos < 1 OR p_quantos > 5000 THEN
    RAISE EXCEPTION 'jobs_semear_demo aceita de 1 a 5000 por chamada, recebeu %', p_quantos USING ERRCODE = 'check_violation';
  END IF;
  IF p_tipo IS NULL OR p_tipo = '' THEN
    RAISE EXCEPTION 'jobs_semear_demo exige o nome do tipo' USING ERRCODE = 'check_violation';
  END IF;

  -- 2.1 nasce pendente e limpo: exatamente o que o gatilho de INSERT da 006 permite a qualquer chamador
  WITH novos AS (
    INSERT INTO plat.job (tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s,
                          agendado_para, criado_em)
    SELECT t, u, p_tipo,
           coalesce(p_parametros, '{}'::jsonb) || jsonb_build_object('semente_demo', true),
           false, 256, 60,
           now() + interval '100 years',            -- nem por acidente sai da fila entre o INSERT e o UPDATE
           now() - (g || ' seconds')::interval
    FROM generate_series(1, p_quantos) AS g
    RETURNING id)
  SELECT array_agg(id) INTO ids FROM novos;

  -- 2.2 transição para o estado final pelo MESMO caminho do worker (a 006 exige o GUC plat.via_worker, cujas
  -- funções plat_app não pode executar; aqui vale porque esta função é SECURITY DEFINER)
  PERFORM plat.via_worker_ligar();
  UPDATE plat.job SET estado = p_estado,
                      progresso = CASE WHEN p_estado = 'concluido' THEN 100 ELSE progresso END,
                      tentativa = 1,
                      worker = 'semente_demo',
                      agendado_para = now() - interval '2 minutes',
                      iniciado_em = now() - interval '2 minutes',
                      terminado_em = now() - interval '1 minute',
                      resultado = CASE WHEN p_estado = 'concluido' THEN jsonb_build_object('semente_demo', true) END,
                      erro = CASE WHEN p_estado <> 'concluido' THEN 'semente de demonstração' END,
                      proveniencia = jsonb_build_object('semente_demo', true, 'em', now())
  WHERE id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM plat.via_worker_desligar();
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.jobs_semear_demo(int, text, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.jobs_semear_demo(int, text, jsonb, text) TO plat_app;
