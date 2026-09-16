-- Conserto de regressão (achado 16/09/2026, tests/api/adversario/test_l0_tenancy.py::
-- test_toda_tabela_com_tenant_id_tem_rls_e_politica): as partições de plat.fluxo_evento
-- (fluxo_evento_202609, fluxo_evento_202610, fluxo_evento_resto, 20260908T1237_fluxo_ingestao.sql) nascem
-- com `relrowsecurity = false` e com GRANT direto a plat_app (default privileges da 001), mesmo o PAI
-- (fluxo_evento) tendo RLS ligada e política por tenant_id.
--
-- MEDIDO ao vivo (trilha uniao), com uma linha de cada inquilino: `SELECT * FROM plat.fluxo_evento` (o
-- PAI) devolve só a linha do inquilino certo — mas `SELECT * FROM plat.fluxo_evento_202609` (a PARTIÇÃO,
-- pelo nome dela) devolvia as linhas dos DOIS inquilinos: RLS do Postgres não propaga sozinha para a
-- partição quando ela é o alvo direto da consulta (só propaga por dentro de uma consulta ao PAI). Também
-- medido: ligar RLS na partição SEM política própria não é suficiente — sem uma policy própria a
-- partição fica em default-deny (nem o dono do dado enxerga a própria linha); a política do pai não é
-- herdada automaticamente pela partição quando ela é consultada pelo nome dela.
--
-- Conserto = o mesmo padrão já usado em plat.rede_medicao_particao_garantir (20260910T2351_rede_medicao.sql):
-- REVOKE ALL da partição (acesso direto por nome fica fechado; o app só enxerga via `plat.fluxo_evento`,
-- que mantém o GRANT e a RLS que já tinha) + RLS ligada + política própria idêntica à do pai, como defesa
-- em profundidade caso algo volte a conceder a tabela sem querer. Aplica nas 3 partições que já existem
-- hoje e muda plat.fluxo_particao_garantir() para fazer o mesmo em toda partição nova, mês que vem incluso.

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_inherits i ON i.inhrelid = c.oid JOIN pg_class p ON p.oid = i.inhparent
    WHERE n.nspname = 'plat' AND p.relname = 'fluxo_evento'
  LOOP
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', r.relname);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', r.relname);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_ler ON plat.%1$I', r.relname);
    EXECUTE format(
      'CREATE POLICY p_%1$s_ler ON plat.%1$I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())',
      r.relname);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_inserir ON plat.%1$I', r.relname);
    EXECUTE format(
      'CREATE POLICY p_%1$s_inserir ON plat.%1$I FOR INSERT TO plat_app WITH CHECK (tenant_id = plat.tenant_atual())',
      r.relname);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_apagar ON plat.%1$I', r.relname);
    EXECUTE format(
      'CREATE POLICY p_%1$s_apagar ON plat.%1$I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())',
      r.relname);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION plat.fluxo_particao_garantir(quando timestamptz DEFAULT now()) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
  ini date := date_trunc('month', quando AT TIME ZONE 'UTC')::date;
  fim date := (date_trunc('month', quando AT TIME ZONE 'UTC') + interval '1 month')::date;
  nome text := 'fluxo_evento_' || to_char(ini, 'YYYYMM');
BEGIN
  IF to_regclass('plat.' || nome) IS NULL THEN
    EXECUTE format('CREATE TABLE plat.%I PARTITION OF plat.fluxo_evento FOR VALUES FROM (%L) TO (%L)',
                   nome, ini, fim);
    -- achado 16/09: sem isto a partição nova herda o GRANT (default privileges da 001) mas NÃO herda RLS
    -- nem política nenhuma — mesmo padrão de plat.rede_medicao_particao_garantir.
    EXECUTE format('REVOKE ALL ON plat.%I FROM plat_app', nome);
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', nome);
    EXECUTE format(
      'CREATE POLICY p_%1$s_ler ON plat.%1$I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())',
      nome);
    EXECUTE format(
      'CREATE POLICY p_%1$s_inserir ON plat.%1$I FOR INSERT TO plat_app WITH CHECK (tenant_id = plat.tenant_atual())',
      nome);
    EXECUTE format(
      'CREATE POLICY p_%1$s_apagar ON plat.%1$I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())',
      nome);
  END IF;
  RETURN nome;
END $$;
