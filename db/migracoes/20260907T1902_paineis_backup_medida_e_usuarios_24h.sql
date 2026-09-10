-- item L7-06-d-paineis: as duas medidas que os painéis "Visão geral" e "Backup e drill" precisam ler
-- e que ainda não existiam no banco. Sem elas os dois painéis mostrariam 'No data' — e a saída seria
-- ou inventar número no painel, ou apagar o painel do portão. Nenhuma das duas serve.
--
-- depende: 20260907T1717_alertas_metrica_fila_backup.sql

-- 1. duração e tamanho da execução de backup/drill. A ROTINA de backup continua sendo outro item;
-- aqui só as colunas e a via de registro, para quem executar poder gravar o que mediu.
ALTER TABLE plat.backup_execucao ADD COLUMN IF NOT EXISTS duracao_s numeric;
ALTER TABLE plat.backup_execucao ADD COLUMN IF NOT EXISTS bytes bigint;

CREATE OR REPLACE FUNCTION plat.backup_registrar(
  p_tipo text, p_ok boolean, p_detalhe text, p_duracao_s numeric, p_bytes bigint)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.backup_execucao (tipo, ok, detalhe, duracao_s, bytes)
  VALUES (p_tipo, p_ok, p_detalhe, p_duracao_s, p_bytes)
$$;
REVOKE EXECUTE ON FUNCTION plat.backup_registrar(text, boolean, text, numeric, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.backup_registrar(text, boolean, text, numeric, bigint) TO plat_app, plat_worker;

-- Agregado cross-instalação da ÚLTIMA execução OK de cada tipo (mesmo padrão SECURITY DEFINER de
-- plat.backup_horas_desde_ultimo). Devolve uma linha por tipo que já teve execução OK; tipo que
-- nunca rodou não aparece — o painel enxerga a ausência, em vez de receber um zero inventado.
CREATE OR REPLACE FUNCTION plat.backup_ultimo()
RETURNS TABLE(tipo text, duracao_s numeric, bytes bigint, executado_em timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT DISTINCT ON (b.tipo) b.tipo, b.duracao_s, b.bytes, b.executado_em
  FROM plat.backup_execucao b
  WHERE b.ok
  ORDER BY b.tipo, b.executado_em DESC
$$;
REVOKE EXECUTE ON FUNCTION plat.backup_ultimo() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.backup_ultimo() TO plat_app;

-- 2. usuários ativos nas últimas 24 h — contagem AGREGADA em todos os inquilinos, lida do log de
-- acesso. Devolve um número só: nenhum rótulo por inquilino, por usuário, por IP ou por token, logo
-- nenhuma cardinalidade nova e nenhum dado pessoal na rota /metrics.
CREATE OR REPLACE FUNCTION plat.usuarios_ativos_24h()
RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(DISTINCT (l.tenant_id, l.usuario_id))::int
  FROM plat.log_acesso l
  WHERE l.em > now() - interval '24 hours' AND l.usuario_id IS NOT NULL
$$;
REVOKE EXECUTE ON FUNCTION plat.usuarios_ativos_24h() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.usuarios_ativos_24h() TO plat_app;
