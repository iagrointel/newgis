-- reaplicavel
-- 20260907T2233_status_amostra (item L0-06-e-status).
-- depende: 20260906T2125_backup_dump_logico.sql
-- Historico de disponibilidade da pagina /status: o periodico `status.amostrar` grava, a cada 5 minutos, uma
-- linha por servico sondado (api, banco, worker, martin, titiler, garage) e a pagina calcula o percentual do
-- mes a partir DESTAS linhas, nunca de numero guardado a mao. Retencao de 90 dias, aplicada na propria
-- gravacao. As funcoes sao SECURITY DEFINER porque /status responde SEM sessao (nao ha inquilino no contexto)
-- e porque a contagem de fila e de backup atravessa todos os inquilinos; por isso cada uma devolve apenas
-- AGREGADO -- nunca nome de inquilino, de arquivo, de bucket ou de maquina. Idempotente.

CREATE TABLE IF NOT EXISTS plat.status_amostra (
  id         bigserial PRIMARY KEY,
  servico    text NOT NULL CHECK (servico ~ '^[a-z][a-z0-9_]{0,30}$'),
  estado     text NOT NULL CHECK (estado IN ('ok','degradado','erro','ausente')),
  criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_status_amostra_em ON plat.status_amostra (criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_status_amostra_servico_em ON plat.status_amostra (servico, criado_em DESC);

-- Sem tenant_id de proposito: isto e telemetria da INSTALACAO (banco, fila, servicos), nao dado de inquilino.
-- Nao ha RLS a aplicar; o acesso e fechado por outro caminho: plat_app nao recebe GRANT nenhum na tabela e so
-- fala com ela pelas funcoes abaixo (mesmo padrao de plat.log_acesso).
REVOKE ALL ON TABLE plat.status_amostra FROM PUBLIC;

-- Grava uma rodada de amostras e apaga o que passou da retencao. Devolve quantas linhas entraram.
CREATE OR REPLACE FUNCTION plat.status_amostrar(p_amostras jsonb, p_dias_retencao int DEFAULT 90) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; dias int;
BEGIN
  dias := least(greatest(coalesce(p_dias_retencao, 90), 1), 3650);
  INSERT INTO plat.status_amostra (servico, estado)
  SELECT a->>'servico', a->>'estado' FROM jsonb_array_elements(coalesce(p_amostras, '[]'::jsonb)) a;
  GET DIAGNOSTICS n = ROW_COUNT;
  DELETE FROM plat.status_amostra WHERE criado_em < now() - make_interval(days => dias);
  RETURN n;
END $$;

-- Apaga as amostras de UM servico. Serve quando um servico sai da instalacao (renomeado, retirado) e o
-- historico dele vira ruido; a suite usa para limpar o servico sintetico que cria ao conferir o percentual.
CREATE OR REPLACE FUNCTION plat.status_amostra_expurgar(p_servico text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.status_amostra WHERE servico = p_servico;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Historico por servico e por dia (a pagina desenha 90 colunas por servico). `ausente` nao conta como queda:
-- fica fora do denominador, porque o subsistema nao existe nesta topologia -- e nao esta fora do ar.
CREATE OR REPLACE FUNCTION plat.status_historico(p_dias int DEFAULT 90)
RETURNS TABLE (servico text, dia date, amostras int, ok int, ausentes int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT s.servico,
         (s.criado_em AT TIME ZONE 'UTC')::date AS dia,
         count(*) FILTER (WHERE s.estado <> 'ausente')::int,
         count(*) FILTER (WHERE s.estado = 'ok')::int,
         count(*) FILTER (WHERE s.estado = 'ausente')::int
    FROM plat.status_amostra s
   WHERE s.criado_em >= now() - make_interval(days => least(greatest(coalesce(p_dias, 90), 1), 3650))
   GROUP BY 1, 2
   ORDER BY 1, 2
$$;

-- Percentual de disponibilidade desde p_desde (a pagina passa o primeiro instante do mes corrente, em UTC).
-- pct = amostras 'ok' sobre amostras que nao sao 'ausente'; sem amostra util, pct e NULL (nunca 100 % fingido).
CREATE OR REPLACE FUNCTION plat.status_disponibilidade(p_desde timestamptz)
RETURNS TABLE (servico text, amostras int, ok int, pct numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT s.servico,
         count(*) FILTER (WHERE s.estado <> 'ausente')::int AS amostras,
         count(*) FILTER (WHERE s.estado = 'ok')::int AS ok,
         CASE WHEN count(*) FILTER (WHERE s.estado <> 'ausente') = 0 THEN NULL
              ELSE round(100.0 * count(*) FILTER (WHERE s.estado = 'ok')
                         / count(*) FILTER (WHERE s.estado <> 'ausente'), 3) END
    FROM plat.status_amostra s
   WHERE s.criado_em >= p_desde
   GROUP BY 1
   ORDER BY 1
$$;

-- Fila em numero: na fila, executando e falhas nas ultimas 24 h, somando todos os inquilinos.
CREATE OR REPLACE FUNCTION plat.status_fila()
RETURNS TABLE (na_fila int, executando int, falhas_24h int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT (SELECT count(*)::int FROM plat.job WHERE estado = 'pendente'),
         (SELECT count(*)::int FROM plat.job WHERE estado = 'rodando'),
         (SELECT count(*)::int FROM plat.job
           WHERE estado = 'falhou' AND terminado_em > now() - interval '24 hours')
$$;

-- Ultimo backup logico: so o agregado da rodada mais recente (instante, quantos esquemas, quantos bytes).
-- Nunca o caminho do arquivo nem o slug do inquilino -- esses ficam em plat.backup, atras do inquilino tecnico.
CREATE OR REPLACE FUNCTION plat.status_backup()
RETURNS TABLE (ultimo_em timestamptz, esquemas int, bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  WITH ultima AS (SELECT max(criado_em) AS em FROM plat.backup),
       rodada AS (SELECT b.* FROM plat.backup b, ultima u
                   WHERE u.em IS NOT NULL AND b.criado_em > u.em - interval '6 hours')
  SELECT (SELECT em FROM ultima), count(*)::int, coalesce(sum(r.bytes), 0)::bigint FROM rodada r
$$;

DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.status_amostrar(jsonb, int)', 'plat.status_amostra_expurgar(text)', 'plat.status_historico(int)',
    'plat.status_disponibilidade(timestamptz)', 'plat.status_fila()', 'plat.status_backup()'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
