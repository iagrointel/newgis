-- item L7-06-b-alertas: duas peças de dado que faltavam para as regras de alerta terem métrica real
-- para ler (em vez de inventar número): (1) idade do job mais antigo RODANDO agora, cross-inquilino,
-- mesmo padrão SECURITY DEFINER de plat.fila_estado() (004); (2) registro mínimo de execução de
-- backup/drill — a rotina de backup em si é OUTRO item (nasce quando esse item for construído); aqui
-- só a TABELA e a FUNÇÃO que o alerta consulta, para o alerta existir e ser testável hoje.

CREATE OR REPLACE FUNCTION plat.fila_job_mais_antigo_rodando_segundos()
RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce(extract(epoch FROM now() - min(iniciado_em))::int, 0)
  FROM plat.job WHERE estado = 'rodando'
$$;
REVOKE EXECUTE ON FUNCTION plat.fila_job_mais_antigo_rodando_segundos() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.fila_job_mais_antigo_rodando_segundos() TO plat_app;

CREATE TABLE IF NOT EXISTS plat.backup_execucao (
  id           bigserial PRIMARY KEY,
  tipo         text NOT NULL CHECK (tipo IN ('backup', 'drill')),
  ok           boolean NOT NULL,
  detalhe      text,
  executado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_backup_execucao_tipo_em ON plat.backup_execucao (tipo, executado_em DESC);
ALTER TABLE plat.backup_execucao ENABLE ROW LEVEL SECURITY;
-- Sem RLS por inquilino: backup é operação da instalação inteira, não de um inquilino. Só a função
-- abaixo (SECURITY DEFINER) grava; leitura pela mesma via de agregado do alerta.
REVOKE ALL ON plat.backup_execucao FROM PUBLIC;

CREATE OR REPLACE FUNCTION plat.backup_registrar(p_tipo text, p_ok boolean, p_detalhe text DEFAULT NULL)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  INSERT INTO plat.backup_execucao (tipo, ok, detalhe) VALUES (p_tipo, p_ok, p_detalhe)
$$;
REVOKE EXECUTE ON FUNCTION plat.backup_registrar(text, boolean, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.backup_registrar(text, boolean, text) TO plat_app, plat_worker;

CREATE OR REPLACE FUNCTION plat.backup_horas_desde_ultimo(p_tipo text)
RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT extract(epoch FROM now() - max(executado_em)) / 3600.0
  FROM plat.backup_execucao WHERE tipo = p_tipo AND ok
$$;
REVOKE EXECUTE ON FUNCTION plat.backup_horas_desde_ultimo(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.backup_horas_desde_ultimo(text) TO plat_app;
