\set ON_ERROR_STOP on
SET search_path = plat_tadv3, public;
BEGIN;
-- isola: adia todo job pendente pre-existente (dentro da transacao; ROLLBACK no fim)
UPDATE job SET agendado_para = now() + interval '1 day' WHERE estado = 'pendente';
CREATE TEMP TABLE t AS SELECT (SELECT id FROM tenant WHERE slug='demo') a, (SELECT id FROM tenant WHERE slug='demo2') b;
INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
  SELECT a, 'zadv3.A', 'X', false, 128, 7200 FROM t;
INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
  SELECT b, 'zadv3.B', 'X', false, 128, 7200 FROM t;
SELECT tipo, tenant_id, chave, estado FROM job WHERE tipo LIKE 'zadv3.%' ORDER BY tipo;
SELECT tipo AS primeiro_pego, tenant_id FROM plat_tadv3.job_pegar('adv3:1', true);
SELECT coalesce((SELECT tipo FROM plat_tadv3.job_pegar('adv3:2', true)), 'NENHUM JOB ELEGIVEL') AS segundo_pego;
SELECT tipo, tenant_id, chave, estado FROM job WHERE tipo LIKE 'zadv3.%' ORDER BY tipo;
ROLLBACK;
