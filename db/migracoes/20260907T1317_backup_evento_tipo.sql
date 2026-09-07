-- Correção do L0-06-a-dump-logico: `_notificar_falha` (app/backup/tarefas.py) tenta registrar o evento
-- 'backup/falha' via plat.evento_registrar, mas plat.evento_tipo nunca ganhou essa linha — o INSERT em
-- plat.evento falha pela FK evento_tipo_fkey, a exceção é engolida (log ERRO, sem levantar) e a notificação
-- vira SILÊNCIO exatamente no caso que o portão de pronto exige auditável (achado do teste_03 real, não de
-- leitura de código: 0 linhas em plat.evento com tipo 'backup/falha' apesar de jobs 'falhou' registrados).
-- Idempotente (ON CONFLICT). Correção em arquivo novo (a 20260906T2125 já foi aplicada).
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('backup/falha', 'rotina de backup lógico falhou (espaço, pg_dump, destino) — evento + e-mail ao superadmin')
ON CONFLICT (nome) DO NOTHING;
